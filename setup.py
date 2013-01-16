from setuptools import setup, find_packages

setup(
    name='sprocket',
    version='1.0',
    description='Easily add an API to a django project.',
    author='Patrick Fitzsimmons',
    author_email='devteam+sprocket@hubspot.com',
    url=' http://hubspot.com/',
    packages=find_packages(),
    install_requires=[
        'Django',
        "hubmockingbird>=1.0,==hubspot",
        ],
    platforms=["any"],
)


