# Drip Lab — built by Rishabh Bhardwaj.
# Personal, non-commercial use only. See LICENSE.

# Runs the free (Hugging Face) edition as a public web app, e.g. on a
# Hugging Face Docker Space. Every visitor gets a private photo and gallery.
FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    DRIPLAB_MULTIUSER=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
