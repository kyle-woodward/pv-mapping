FROM tensorflow/tensorflow:latest-gpu

# Set the timezone
ENV TZ=America/Los_Angeles
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Update and install apt dependencies 
RUN apt-get update && apt-get install -y \
    libyaml-dev \
    curl \
    && apt-get clean

# Install Python dependencies with pip
RUN pip install \
    PyYAML \
    rasterio \
    matplotlib \
    numpy \
    pandas \
    geopandas

# install GCloud CLI    
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | \
    tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
    apt-key --keyring /usr/share/keyrings/cloud.google.gpg  add - \
    && apt-get update -y && apt-get install google-cloud-cli -y

# Set the default command to bash
CMD ["/bin/bash"]
