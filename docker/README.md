## Prepare the inspire-validator

Execute the following commands inside this directory:

```bash
wget https://github.com/inspire-eu-validation/community/releases/download/v2020.3/inspire-validator-2020.3.zip
unzip -d inspire-validator inspire-validator-2020.3.zip
rm inspire-validator-2020.3.zip
```

## Prepare the ETF test suite

Execute the following commands inside this directory:

```bash
mkdir -p etf/ds/db/repo/BaseXRepo
unzip -d etf/ds/db/repo/BaseXRepo functx-1.0.xar
chmod -R 777 etf
sudo chown -R 999:999 etf
```

## Start docker containers

```bash
docker-compose -f docker-compose-dev.yml up
```