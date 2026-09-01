FROM python:3.12-slim

WORKDIR /email_classifier

# The bot imports app.helpers.enums, so the whole project is installed; only the
# bot extra's runtime deps come with it.
COPY . .
RUN pip install --no-cache-dir ".[bot]"

RUN useradd --create-home --uid 1000 bot && chown -R bot:bot /email_classifier
USER bot

CMD ["python", "-m", "bot"]
