from google.cloud import secretmanager
import os
from flask import jsonify
import redis
import tempfile
import psycopg2

client = secretmanager.SecretManagerServiceClient()
project_id = "pure-imagery-464210-j7"

def get_secret(secret_name):
    secret_path =  f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    output = client.access_secret_version(name=secret_path)
    secret = output.payload.data.decode("UTF-8")
    return secret

def write_to_file(content, suffix = ".crt"):
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="w")
    temp.write(content)
    temp.close()
    return temp.name


def main(request):
    temp_files = []
    conn = None

    try:
        print("⏳ Starting secret retrieval...")
        # Get secret names from env.
        db_host = get_secret(os.environ["DB_HOST"]) 
        db_name = get_secret(os.environ["DB_NAME"])
        db_user = get_secret(os.environ["DB_USER"])
        db_password = get_secret(os.environ["DB_PASSWORD"])
        redis_host = get_secret(os.environ["REDIS_HOST"])
        redis_port = int(get_secret(os.environ["REDIS_PORT"]))
        redis_password = get_secret(os.environ["REDIS_PASSWORD"])
        # redis_cert = get_secret(os.environ["REDIS_CERT"])
        # client_key = get_secret(os.environ["DB_CLIENT_KEY"])
        # server_ca = get_secret(os.environ["DB_SERVER_CA"])
        print("✅ Secrets loaded")
    
        # Write certs to temporary files
        client_cert_path = write_to_file(get_secret(os.environ["DB_CLIENT_CERT"]), ".crt")
        client_key_path = write_to_file(get_secret(os.environ["DB_CLIENT_KEY"]), ".key")
        server_ca_path = write_to_file(get_secret(os.environ["DB_SERVER_CA"]), ".crt")
        redis_cert_path = write_to_file(get_secret(os.environ["REDIS_CERT"]), ".crt")

        temp_files.extend([client_cert_path, client_key_path, server_ca_path, redis_cert_path])
        print("🔐 Secrets and certificates loaded")

        # Connect to Cloud SQL
        print("🔌 Connecting to Postgres...")
        conn = psycopg2.connect(
            host=db_host,
            # hostaddr=db_host,
            dbname=db_name,
            user=db_user,
            password=db_password,
            # sslmode="verify-full",
            sslmode="require",
            sslcert=client_cert_path,
            sslkey=client_key_path,
            sslrootcert=server_ca_path, 
        )

        # Connect to Redis
        print("🔌 Connecting to Redis...")

        r = redis.StrictRedis(
            host=redis_host, 
            port=redis_port, 
            password=redis_password,
            ssl=True, 
            ssl_cert_reqs='required',
            ssl_ca_certs=redis_cert_path,
            decode_responses=True
        )
        print("✅ Redis client created")
        print("💾 Writing to Redis...")


        r.set('name', 'Test Name')
        print("✅ Redis connected and test key set")

        value_from_redis = r.get('name')
        print("📦 Fetched value from Redis")

        return jsonify({
            "message": f"Hello, connection established db host{db_host} redis_value{value_from_redis}!"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        # Clean up temporary files
        for path in temp_files:
            if path and os.path.exists(path):
                os.remove(path)
        if conn:
            conn.close()