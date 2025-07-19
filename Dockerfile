FROM public.ecr.aws/lambda/python:3.10

WORKDIR /code

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY src/ .

ENV PYTHONPATH=.

CMD [ "main.handler" ]