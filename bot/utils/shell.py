# Developed by ARGON telegram: @REACTIVEARGON
import io

# Function to execute Python code


async def run_python_code(code: str):
    try:
        local_vars = {}
        output_buffer = io.StringIO()  # Capture print() output
        exec_globals = {
            "__builtins__": globals()["__builtins__"],
            "print": lambda *args, **kwargs: print(*args, **kwargs, file=output_buffer),
        }

        exec(code, exec_globals, local_vars)  # Execute the script

        output = output_buffer.getvalue().strip()  # Get print() output
        if not output:
            # Check for a variable output
            output = local_vars.get("output", "Executed successfully with no output.")

        return output
    except Exception as e:
        print(f"Error:- {e}")


# Command to execute Python scripts


async def shell_command(client, message):
    if not message.reply_to_message:
        return await message.reply(
            "Reply to a message containing Python code or a .py file."
        )

    if message.reply_to_message.document:
        file = await message.reply_to_message.download()
        with open(file, "r", encoding="utf-8") as f:
            code = f.read()
    else:
        code = message.reply_to_message.text

    response = await run_python_code(code)
    await message.reply(f"**Output:**\n```python\n{response}\n```", quote=True)
