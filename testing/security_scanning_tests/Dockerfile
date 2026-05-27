FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY testing/security_scanning_tests/*.py /app/

CMD ["bash"]
