FROM python:3.10

RUN apt-get update && \
    apt-get install -y locales wget chromium && \
    sed -i -e 's/# nl_NL.UTF-8 UTF-8/nl_NL.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

ENV LANG nl_NL.UTF-8
ENV LC_ALL nl_NL.UTF-8

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./*.py /code/

CMD ["python", "main.py"]