# Optimized image (smaller base, fewer deps).
# Biggest dependency remains Firefox.
FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive

# Runtime deps only; no recommended extras; clean apt lists.
# Note: we do NOT install geckodriver here; Selenium 4 includes Selenium Manager
# which can fetch a compatible driver at runtime.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      firefox-esr \
      locales \
      ca-certificates \
      curl \
 && rm -rf /var/lib/apt/lists/*

# Locale needed for Dutch date parsing
RUN sed -i -e "s/# nl_NL.UTF-8 UTF-8/nl_NL.UTF-8 UTF-8/" /etc/locale.gen \
 && locale-gen

ENV LANG=nl_NL.UTF-8
ENV LC_ALL=nl_NL.UTF-8

WORKDIR /code

COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /code/requirements.txt

COPY ./*.py /code/

# NOTE: Hue bridge credentials are stored in the image currently.
# Consider moving this to a mounted secret/config later.
RUN mkdir -p /root \
 && echo '{"192.168.2.4": {"username": "1Uxtrwx1xBu8Nv9V0o9zkxdKOa5g8QMgLGA6efDb"}}' > /root/.python_hue

CMD ["python", "main.py"]
