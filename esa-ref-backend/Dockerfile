# Linux image: OpenCode (agent engine, free opencode/* models) + FastAPI job server in one container.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://opencode.ai/install | bash
ENV PATH="/root/.opencode/bin:/root/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
WORKDIR /app
RUN mkdir fonts && curl -fsSL -o fonts/NotoSansCJKtc-Bold.otf https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Bold.otf
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
ENV OPENCODE_URL=http://127.0.0.1:4096 OPENCODE_MODEL=opencode/glm-5.3-flash-free
EXPOSE 8000
VOLUME /app/data
CMD ["bash", "scripts/start.sh"]
