# MiniDropBox

MiniDropBox is a simple user-friendly file sharing application. The application facilitates file upload, download, share, delete, recover and remote access. 

## Installation
Python and Flask framework is used to develop this website with PyCharm IDE as an editor and MYSQL Workbench for backend. 

Clone the repository:
```bash
git clone https://github.com/KrishReigns/MiniDropBox.git
cd MiniDropBox
```

## Set Up Virtual Environment:

```
python -m venv venv
source venv/bin/activate  # On Windows, use venv\Scripts\activate
```

## Install Dependencies:

```
pip install -r requirements.txt
```
## Configure AWS Services:

Set up AWS IAM roles and permissions for S3, SES, EC2, and VPC.
Configure AWS RDS for MySQL database and note down the connection details.

## Set Environment Variables:
Create a .env file in the project root and add the following environment variables:

```
FLASK_APP=app.py
FLASK_ENV=development  # Change to production for deployment
SECRET_KEY=your_secret_key  # Generate a strong secret key
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_DEFAULT_REGION=your_aws_region
AWS_BUCKET_NAME=your_s3_bucket_name
AWS_BUCKET_REGION=your_s3_bucket_region
AWS_RDS_HOST=your_rds_host
AWS_RDS_PORT=your_rds_port
AWS_RDS_DBNAME=your_rds_database_name
AWS_RDS_USERNAME=your_rds_username
AWS_RDS_PASSWORD=your_rds_password

```

## Access the Application:
Run Main.py 
Open your web browser and visit http://localhost:5000 to access the MiniDropBox application.