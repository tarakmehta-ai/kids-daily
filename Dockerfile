FROM python:3.11-slim

# HuggingFace Spaces run the container as uid 1000; anything we write to must
# be owned by that user.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CACHE_DIR=/home/user/cache

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /home/user/cache && chown -R user:user /home/user /app

USER user
EXPOSE 7860

# Shell form on purpose: $PORT must expand at runtime. Render assigns a port
# and rejects the deploy if we bind anything else; 7860 is the fallback for
# local runs and for HuggingFace Spaces.
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-7860}
