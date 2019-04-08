FROM python:latest

RUN mkdir /cookidump
RUN mkdir /cookidump/recipes
ADD cookidump.py /cookidump/
ADD requirements.txt /cookidump/

RUN pip install -r /cookidump/requirements.txt