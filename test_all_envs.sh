#!/usr/bin/env bash

USER_VERSION=$(pyenv local)

for version in 2.7.14 3.5.7 3.6.{7,8} 3.7.{1,2};
do
    echo -e "\n\n --- ${version} --- \n\n";
    pyenv install "${version}" --skip-existing;
    pyenv local "${version}";
    pip install tox;
    tox;
done;

pyenv local "${USER_VERSION}"
