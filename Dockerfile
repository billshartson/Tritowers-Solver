FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 1000 app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app app.py web_app.py web_shared.py solver_ui.py solver.py tritowers_cli.py MODEL_CARD.md ./
COPY --chown=app:app web/ ./web/
COPY --chown=app:app tritowers_vision/ ./tritowers_vision/
USER app
ENV HOST=0.0.0.0 PORT=7860 GRADIO_ANALYTICS_ENABLED=False
EXPOSE 7860
CMD ["python", "app.py"]
