import ee

"""
curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-468.0.0-linux-x86_64.tar.gz
tar -xf google-cloud-cli-468.0.0-linux-x86_64.tar.gz
./google-cloud-sdk/install.sh
./google-cloud-sdk/install.sh --help
./google-cloud-sdk/bin/gcloud init
gcloud init
"""


ee.Authenticate()
ee.Initialize(project='my-project')