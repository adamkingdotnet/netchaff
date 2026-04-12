FROM python:3.14-alpine

RUN pip install --no-cache-dir requests==2.33.1

COPY netchaff.py /netchaff.py
COPY config.json /config.json

ENTRYPOINT ["python", "/netchaff.py"]
CMD ["--config", "/config.json"]
