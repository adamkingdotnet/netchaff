FROM python:3.14-alpine

RUN pip install --no-cache-dir requests==2.33.1

COPY noisy.py /noisy.py

ENTRYPOINT ["python", "/noisy.py"]
