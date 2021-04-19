FROM python:3.7-buster
ENV PYTHONUNBUFFERED=1
WORKDIR /opt/mrmap
RUN pip install -r requirements.txt
RUN python manage.py migrate




