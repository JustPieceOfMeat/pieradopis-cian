FROM python

ADD main.py requirements.txt /

RUN pip install -r /requirements.txt

ENV DOCKER=TRUE

VOLUME /sessions

CMD python /main.py

