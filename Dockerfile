FROM python:3.13-slim
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

COPY api/ api/
COPY service/ service/
COPY util/ util/
COPY web/ web/

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host" ,"0.0.0.0"]