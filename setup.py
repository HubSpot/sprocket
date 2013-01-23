from setuptools import setup, find_packages

setup(
    name='sprocket',
    version='0.1',
    description='Web API organization with Mixins.',
    author='Patrick Fitzsimmons',
    author_email='pfitzsimmons@hubspot.com',
    url=' http://hubspot.com/',
    packages=find_packages(),
    install_requires=[
        'Django',
        ],
    platforms=["any"],
)
