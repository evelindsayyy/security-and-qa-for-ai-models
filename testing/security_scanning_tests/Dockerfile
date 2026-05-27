FROM python:3.11-slim

# everything runs from /app inside the container
WORKDIR /app

# install dependencies in the container, not on the dgx host
RUN pip install --no-cache-dir \
    huggingface_hub \
    modelscan \
    fickling

# copy our scripts into the image at build time
# models/ and output/ are mounted at runtime (see docker-compose.yml)
COPY *.py /app/

# default: drop you into a shell so you can run scripts one at a time
CMD ["bash"]
