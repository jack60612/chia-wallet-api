FROM ubuntu:20.04
# define needed vars for apt and app
WORKDIR /app
ENV DEBIAN_FRONTEND = noninteractive
ENV CHIA_ROOT="/mnt/chia/.chia/mainnet"
# install dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y git python3-venv python3-pip lsb-release sudo bc
# copy pool-reference files
COPY ./server /app/server
# copy config files
COPY ./config.yaml /app/config.yaml
# install chia blockchain module
RUN pip install wheel
RUN pip install chia-blockchain
# install sanic and other dependencies
RUN pip install sanic
# run pool
CMD python3 -m server
# expose ports
EXPOSE 8080

