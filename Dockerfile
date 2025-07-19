FROM public.ecr.aws/lambda/python:3.10

ADD src/ /code

WORKDIR /code

COPY requirements.txt .

RUN pip install -r requirements.txt

ENV PYTHONPATH=.

CMD [ "main.handler" ]