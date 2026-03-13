## Set up Python virtual environment

Usefull so that everyone involved in the project can use the same Python version and packages (and other python versions/packages in other projects)

 

1. Install [pyenv](https://github.com/pyenv/pyenv) with this command:

```shell

curl https://pyenv.run | bash

```

 

2. Add some lines to `.bashrc` with these commands:

```shell

echo '# Load pyenv' >> ~/.bashrc

echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc

echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc

echo 'eval "$(pyenv init -)"' >> ~/.bashrc

echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc

```

 

3. Restart your shell with this command:

```shell

exec "$SHELL"

```

 

4. Run the following command to install packages required for pyenv:

```shell

sudo apt-get -y install build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev libncurses-dev tk-dev

```

 

5. Create a Python virtual environment ([pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv)) with the following commands:

```shell

pyenv install 3.10.12

pyenv virtualenv 3.10.12 furigana-bot-3.10.12

```

 

5. Navigate to the project directory and run the following command to assign the Python virtual environment for this project:

```shell

pyenv local furigana-bot-3.10.12

```

 

6. Run this command:

```shell

python --version

```

The output should show `3.10.12`.

 

7. Navigate to the project directory again and install the packages used in the project with this command:

```shell

pip install -r requirements.txt

```

When installing new packages, you can update the requirements file with this command:

```shell

pip freeze > requirements.txt

```

 

The Python virtual environment should now be activated automatically when navigating to the project directory (or a subdirectory), and deactivated when navigating outside the project directory. It can also be used in Jupyter notebooks by opening the a notebook, clicking on the Python version in the top right, and selecting `furigana-bot-3.10.12 (Python 3.10.12) ~./pyenv/versions/furigana-bot-3.10.12/bin/python`.