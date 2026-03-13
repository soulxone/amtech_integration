from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="amtech_integration",
    version="0.1.0",
    description="Amtech Encore ERP / Sign & Drive integration for ERPNext",
    author="Welch Packaging",
    author_email="soulxone@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
