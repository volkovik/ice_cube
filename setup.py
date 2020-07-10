from setuptools import setup, find_packages

setup(
    name="Ice_Cube",
    version="0.2a1",
    packages=find_packages(),
    install_requires=["discord.py>=1.3.4", "mysql-connector-python>=8.0.0"],
    python_requires="==3.7",
    author="Daniil Syurmachenko",
    author_email="vxlkxvik@yandex.ru",
    url="https://github.com/volkovik/ice_cube",
    license="GPL-3.0"
)
