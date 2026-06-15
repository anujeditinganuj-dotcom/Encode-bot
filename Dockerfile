# Base Image
FROM fedora:40

# 1. Setup home directory, non interactive shell and timezone
RUN mkdir -p /bot /tgenc && chmod 777 /bot
WORKDIR /bot

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Africa/Lagos
ENV TERM=xterm

# 2. Install Dependencies (including git)
RUN dnf -qq -y update \
    && dnf -qq -y install \
       git \
       aria2 \
       bash \
       xz \
       wget \
       curl \
       pv \
       jq \
       python3-pip \
       mediainfo \
       psmisc \
       procps-ng \
       qbittorrent-nox \
    && if [ "$(arch)" = "aarch64" ]; then \
         dnf -qq -y install gcc python3-devel; \
       fi \
    && python3 -m pip install --upgrade pip setuptools \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 3. Install latest ffmpeg
RUN arch=$(arch | sed 's/aarch64/arm64/' | sed 's/x86_64/64/') && \
    wget -q "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux${arch}-gpl-7.1.tar.xz" && \
    tar -xJf ffmpeg-n7.1-latest-linux${arch}-gpl-7.1.tar.xz && \
    cp -a */bin/* /usr/bin/ && \
    rm -rf ffmpeg-n7.1-latest-linux${arch}-gpl-7.1* || true

# 4. Copy files from repo to home directory
COPY . .

# 5. Install python3 requirements
RUN pip3 install -r requirements.txt

# 6. cleanup for arm64
RUN if [ "$(arch)" = "aarch64" ]; then \
      dnf -qq -y history undo last; \
    fi && dnf clean all

# 7. Start bot
CMD ["bash","start.sh"]