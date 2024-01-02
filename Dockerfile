# Older ubuntu without snapd
FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt update
RUN apt install -y locales python3 python3-pip firefox firefox-geckodriver

# Needed to parse dates from Dutch
RUN locale-gen nl_NL
RUN sed -i -e 's/# nl_NL.UTF-8 UTF-8/nl_NL.UTF-8 UTF-8/' /etc/locale.gen
RUN dpkg-reconfigure --frontend=noninteractive locales

ENV LANG nl_NL.UTF-8
ENV LC_ALL nl_NL.UTF-8

# Save the username for the Hue bridge, so we don't have to pair every time
RUN echo '{"192.168.50.11": {"username": "m8szYhUyVGJbwEDFcsIzOcueVCoioH6IN5aluepO"}}' > /root/.python_hue

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip3 install --no-cache-dir --upgrade -r /code/requirements.txt

COPY ./*.py /code/

CMD ["python3", "main.py"]
