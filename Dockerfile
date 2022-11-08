FROM python:3.8

RUN apt-get update -y
#RUN apt-get install -y python-pip python-dev build-essential

COPY ./src/requirements.txt /src/

WORKDIR /src
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src/*.py /src/

ENTRYPOINT ["python3", "./org_visualise.py"]
