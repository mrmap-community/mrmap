# debian 11 image
FROM python:3-bullseye

WORKDIR ./app

# todo check if all this packages are still needed...
RUN apt-get -qq update && \
    apt-get -y install libcurl4-openssl-dev libssl-dev gdal-bin libpq-dev gcc

# By copying over requirements first, we make sure that Docker will cache
# our installed requirements rather than reinstall them on every build
COPY ./mrmap/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Now copy in our code, and run it
COPY . /mrmap
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]