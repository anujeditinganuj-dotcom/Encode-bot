# Developed by ARGON telegram: @REACTIVEARGON
import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from bot.logger import LOGGER
from database import get_variable, set_variable

log = LOGGER(__name__)


@dataclass
class Job:
    job_id: str
    user_id: int
    func: Callable[..., Awaitable[Any]]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, running, completed, failed, cancelled
    file_size: str = "Unknown"
    file_name: str = "Unknown"
    chat_id: int = 0
    message_id: int = 0
    task_type: str = "generic"
    input_file: str = ""
    output_file: str = ""

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "status": self.status,
            "file_size": self.file_size,
            "file_name": self.file_name,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "task_type": self.task_type,
            "input_file": self.input_file,
            "output_file": self.output_file,
            "args": self.args,
            "kwargs": self.kwargs,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            job_id=data["job_id"],
            user_id=data["user_id"],
            func=None,  # Must be re-attached
            status=data["status"],
            file_size=data.get("file_size", "Unknown"),
            file_name=data.get("file_name", "Unknown"),
            chat_id=data.get("chat_id", 0),
            message_id=data.get("message_id", 0),
            task_type=data.get("task_type", "generic"),
            input_file=data.get("input_file", ""),
            output_file=data.get("output_file", ""),
            args=tuple(data.get("args", ())),
            kwargs=data.get("kwargs", {}),
        )


class QueueManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QueueManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._queue = asyncio.Queue()
        self._active_jobs: Dict[str, Job] = {} # Changed from _active_job to dict
        self._jobs: Dict[str, Job] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(4) # Limit concurrent jobs
        self._initialized = True
        log.info("QueueManager initialized with 4 concurrent slots")

    async def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())
            log.info("QueueManager worker started")

    async def save_queue(self):
        try:
            # Save only pending and running jobs
            # For running jobs, we save them as pending so they restart
            jobs_data = []
            for job in self._jobs.values():
                if job.status in ["pending", "running"]:
                    job_dict = job.to_dict()
                    # If it was running, mark as pending for restart
                    if job_dict["status"] == "running":
                        job_dict["status"] = "pending"
                    jobs_data.append(job_dict)

            await set_variable("queue_state", jobs_data)
        except Exception as e:
            log.error(f"Failed to save queue: {e}")

    async def restore_queue(self, client):
        try:
            jobs_data = await get_variable("queue_state", [])
            if not jobs_data:
                log.info("Got none older queue")
                return

            log.info(f"Restoring {len(jobs_data)} jobs from database...")

            # Import here to avoid circular dependency
            from bot.func.encode import reconstruct_worker

            for data in jobs_data:
                job = Job.from_dict(data)

                if job.task_type == "encode":
                    # Reconstruct the worker function
                    job.func = reconstruct_worker(job, client)

                    # Fix for legacy jobs without args
                    if not job.args:
                        job.args = (job.job_id,)

                    self._jobs[job.job_id] = job
                    await self._queue.put(job)
                    log.info(f"Restored job {job.job_id}")

            if self._jobs:
                await self.start()

        except Exception as e:
            log.error(f"Failed to restore queue: {e}")

    async def add_job(
        self,
        user_id: int,
        func: Callable[..., Awaitable[Any]],
        *args,
        file_size: str = "Unknown",
        file_name: str = "Unknown",
        chat_id: int = 0,
        message_id: int = 0,
        task_type: str = "generic",
        input_file: str = "",
        output_file: str = "",
        **kwargs,
    ) -> Optional[str]:
        # Check for duplicates
        if file_name != "Unknown":
            for job in self._jobs.values():
                if (
                    job.user_id == user_id
                    and job.file_name == file_name
                    and job.status in ["pending", "running"]
                ):
                    log.warning(
                        f"Duplicate job attempt by user {user_id} for file {file_name}"
                    )
                    return None

        job_id = str(uuid.uuid4())[:8]
        job = Job(
            job_id=job_id,
            user_id=user_id,
            func=func,
            args=args,
            kwargs=kwargs,
            file_size=file_size,
            file_name=file_name,
            chat_id=chat_id,
            message_id=message_id,
            task_type=task_type,
            input_file=input_file,
            output_file=output_file,
        )
        self._jobs[job_id] = job
        await self._queue.put(job)
        log.info(f"Job {job_id} added to queue for user {user_id}")

        await self.save_queue()

        # Ensure worker is running
        if self._worker_task is None or self._worker_task.done():
            await self.start()

        return job_id

    async def cancel_job(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False

        job = self._jobs[job_id]

        # Helper to clean files
        def clean_files(j: Job):
            import os

            try:
                if j.input_file and os.path.exists(j.input_file):
                    os.remove(j.input_file)
                    log.info(f"Removed input file for job {j.job_id}: {j.input_file}")
                if j.output_file and os.path.exists(j.output_file):
                    os.remove(j.output_file)
                    log.info(f"Removed output file for job {j.job_id}: {j.output_file}")
            except Exception as e:
                log.error(f"Failed to clean files for job {j.job_id}: {e}")

        if job.status == "running":
            job.status = "cancelled"
            log.info(f"Job {job_id} marked for cancellation")

            # If job is active, we rely on the job logic to handle cancellation check
            # But we can also try to cancel the specific task if we tracked it?
            # For now, we just mark it. The encode process checks `is_cancelled` flag.
            # And we clean files.

            await self.save_queue()
            return True

        elif job.status == "pending":
            job.status = "cancelled"
            log.info(f"Pending job {job_id} cancelled")
            clean_files(job)  # Clean files immediately for pending jobs
            await self.save_queue()
            return True

        return False

    async def clear_queue(self):
        """Cancels all pending jobs and clears the queue."""
        log.info("Clearing queue...")

        # Cancel all pending jobs
        for job in list(self._jobs.values()):
            if job.status == "pending":
                await self.cancel_job(job.job_id)

        # We can't easily empty the asyncio.Queue without getting everything.
        # But since we marked them as cancelled, the worker will skip them.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break

        await self.save_queue()
        log.info("Queue cleared")

    async def _worker(self):
        log.info("Queue worker loop started")
        while True:
            try:
                job = await self._queue.get()

                if job.status == "cancelled":
                    log.info(f"Skipping cancelled job {job.job_id}")
                    self._queue.task_done()
                    await self.save_queue()
                    continue

                # Acquire semaphore slot before spawning task.
                # This blocks here (not inside the task) so the worker loop
                # naturally throttles to _semaphore count concurrent jobs.
                await self._semaphore.acquire()

                # Spawn task — semaphore is released in _process_job's finally block.
                asyncio.create_task(self._process_job(job))

            except Exception as e:
                log.error(f"Error in queue worker: {e}")
                await asyncio.sleep(1)

    async def _process_job(self, job: Job):
        try:
            # Check status again in case it was cancelled while waiting?
            if job.status == "cancelled":
                self._queue.task_done()
                return

            self._active_jobs[job.job_id] = job
            job.status = "running"
            await self.save_queue()
            log.info(f"Starting job {job.job_id}")

            try:
                await job.func(*job.args, **job.kwargs)
                job.status = "completed"
            except asyncio.CancelledError:
                job.status = "cancelled"
                log.info(f"Job {job.job_id} was cancelled during execution")
            except Exception as e:
                job.status = "failed"
                log.error(f"Job {job.job_id} failed: {e}")
            finally:
                if job.job_id in self._active_jobs:
                    del self._active_jobs[job.job_id]
                self._queue.task_done()
                await self.save_queue()
        finally:
            self._semaphore.release()

    def get_user_jobs(self, user_id: int) -> list[Job]:
        return [
            job
            for job in self._jobs.values()
            if job.user_id == user_id and job.status in ["pending", "running"]
        ]

    def get_all_jobs(self) -> list[Job]:
        return [
            job for job in self._jobs.values() if job.status in ["pending", "running"]
        ]

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)


queue_manager = QueueManager()
