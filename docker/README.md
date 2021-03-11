## Prepare the inspire-validator

Execute the following commands inside this directory:

```bash
wget https://github.com/inspire-eu-validation/community/releases/download/v2020.3.1/inspire-validator-2020.3.1.zip
unzip -d inspire-validator inspire-validator-2020.3.1.zip
rm inspire-validator-2020.3.1.zip
```

## Start docker containers

```bash
docker-compose -f docker-compose-dev.yml up --build
```
