#! /usr/bin/env python3

"""An interactive script to configure ODK-X sync endpoint on first run.

This script supports both Let's Encrypt and self-signed certificates.
"""
import time
import os
import re
import shutil
import subprocess
from tempfile import mkstemp
from shutil import move, copymode
from os import fdopen, remove
from pathlib import Path

def ensure_directory_exists(directory):
    """Creates directory if it doesn't exist with proper permissions."""
    try:
        if not os.path.exists(directory):
            os.makedirs(directory, mode=0o755, exist_ok=True)
            print(f"Created directory: {directory}")
        return True
    except Exception as e:
        print(f"Error creating directory {directory}: {str(e)}")
        return False

def setup_certificate_paths(use_existing=False):
    """Sets up certificate paths and handles certificate copying if using existing certs."""
    # Get the script's directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define certificate paths
    existing_cert_dir = "/etc/ssl/odkx"
    target_cert_dir = os.path.join(script_dir, "..", "certs")
    
    # Ensure directories exist
    if use_existing:
        if not os.path.exists(existing_cert_dir):
            print(f"\nWarning: Source certificate directory {existing_cert_dir} does not exist")
            print("Creating directory structure...")
            ensure_directory_exists(existing_cert_dir)
    
    # Always ensure target directory exists
    ensure_directory_exists(target_cert_dir)
    
    if use_existing:
        print(f"\nUsing certificates from {existing_cert_dir}")
        return existing_cert_dir, target_cert_dir
    else:
        return None, target_cert_dir

def copy_existing_certificates(source_dir, target_dir):
    """Copies existing certificates from source to target directory."""
    try:
        # Define certificate files to copy
        cert_files = {
            'fullchain.pem': 'fullchain.pem',
            'privkey.pem': 'privkey.pem'
        }
        
        print(f"\nCopying certificates from {source_dir} to {target_dir}")
        
        # Copy each certificate file
        for source_file, target_file in cert_files.items():
            source_path = os.path.join(source_dir, source_file)
            target_path = os.path.join(target_dir, target_file)
            
            if os.path.exists(source_path):
                shutil.copy2(source_path, target_path)
                # Set appropriate permissions
                os.chmod(target_path, 0o600)
                print(f"Copied: {source_file}")
            else:
                print(f"Warning: Certificate file not found: {source_path}")
                print("You will need to manually copy your certificates later.")
                
        print("Certificate copying completed.")
        
    except Exception as e:
        print(f"Error copying certificates: {str(e)}")
        raise

def create_self_signed_cert(domain, email, cert_dir):
    """Creates a self-signed certificate for the domain."""
    try:
        print(f"\nCreating self-signed certificate for {domain}")
        
        # Ensure directory exists
        ensure_directory_exists(cert_dir)
        
        # Define certificate paths
        key_path = os.path.join(cert_dir, "privkey.pem")
        cert_path = os.path.join(cert_dir, "fullchain.pem")
        
        # Create the certificate
        cmd = [
            "openssl", "req", "-x509", "-nodes", 
            "-days", "365", "-newkey", "rsa:2048",
            "-keyout", key_path,
            "-out", cert_path,
            "-subj", f"/CN={domain}/emailAddress={email}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error creating self-signed certificate: {result.stderr}")
            return False
        
        # Set appropriate permissions
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
        
        print("Self-signed certificate created successfully.")
        return True
        
    except Exception as e:
        print(f"Error creating self-signed certificate: {str(e)}")
        return False

def run_interactive_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file_location = os.path.join(script_dir, "config", "https.env")

    # Create config directory if it doesn't exist
    config_dir = os.path.join(script_dir, "config")
    ensure_directory_exists(config_dir)

    # Check if env file exists, create it with defaults if not
    if not os.path.exists(env_file_location):
        print(f"No config file found at {env_file_location}, creating with defaults.")
        with open(env_file_location, "w") as f:
            f.write("HTTPS_DOMAIN=localhost\n")
            f.write("HTTPS_ADMIN_EMAIL=admin@example.com\n")
        domain = "localhost"
        email = "admin@example.com"
    else:
        try:
            domain, email = parse_env_file(env_file_location)
            print("Found configuration at {}".format(env_file_location))
        except Exception as e:
            print(f"Error parsing config file: {str(e)}")
            domain = "localhost"
            email = "admin@example.com"
            print("Using default values instead.")

    print("\nWelcome to the ODK-X sync endpoint installation!")
    print("This script will guide you through setting up your installation")
    print("We'll need some information from you to get started though...")
    time.sleep(1)
    print("")
    print("Please input the domain name you will use for this installation. A valid domain name is required for HTTPS without distributing custom certificates.")
    input_domain = input("domain [({})]: ".format(domain))

    if input_domain != "":
        domain = input_domain

    print("")
    use_custom_password = input("Do you want to use a custom LDAP administration password (y/N)? ")
    if use_custom_password.lower().strip() == "y":
        print("")
        print("Please input the password to use for ldap admin")
        default_ldap_pwd = input("Ldap admin password: ")

        if default_ldap_pwd != "":
            ldap_env_path = os.path.join(script_dir, "ldap.env")
            if os.path.exists(ldap_env_path):
                replaceInFile(ldap_env_path, r"^\s*LDAP_ADMIN_PASSWORD=.*$", "LDAP_ADMIN_PASSWORD={}".format(default_ldap_pwd))
                print("Password set to: {}".format(default_ldap_pwd))
            else:
                print(f"Warning: ldap.env file not found at {ldap_env_path}")
                print("Creating ldap.env file with your password...")
                with open(ldap_env_path, "w") as f:
                    f.write(f"LDAP_ADMIN_PASSWORD={default_ldap_pwd}\n")
                print("ldap.env file created.")

    while True:
        print("Would you like to enforce HTTPS? We recommend yes.")
        enforce_https = input("enforce https [(Y)/n]: ")
        if enforce_https == "":
            enforce_https = "y"
        enforce_https = enforce_https.lower().strip()[0]
        if enforce_https in ["y", "n"]:
            break

    if enforce_https == "n":
        print("Would you like to run an INSECURE and DANGEROUS server that will share your users's information if exposed to the Internet?")
        insecure = input("run insecure [y/(N)]: ")
        if insecure == "":
            insecure = "n"
        if insecure.lower().strip()[0] != "y":
            raise RuntimeError("HTTPS is currently required to run a secure public server. Please restart and select to enforce HTTPS")

    enforce_https = enforce_https == "y"

    print("Enforcing https:", enforce_https)
    if enforce_https:
        print("\nHow would you like to configure HTTPS?")
        print("1. Use existing certificates from /etc/ssl/odkx")
        print("2. Create self-signed certificates (easiest option)")
        print("3. Request Let's Encrypt certificates (requires port 80 to be available)")
        
        cert_choice = input("\nEnter your choice (1-3) [2]: ")
        if cert_choice == "":
            cert_choice = "2"
        
        if cert_choice == "1":
            # Use existing certificates
            source_dir, target_dir = setup_certificate_paths(use_existing=True)
            copy_existing_certificates(source_dir, target_dir)
        elif cert_choice == "2":
            # Create self-signed certificates
            print("Please provide an admin email for the certificate")
            input_email = input("admin email [({})]: ".format(email))
            if input_email != "":
                email = input_email
                
            # Create certificates in /etc/ssl/odkx
            ssl_dir = "/etc/ssl/odkx"
            ensure_directory_exists(ssl_dir)
            success = create_self_signed_cert(domain, email, ssl_dir)
            
            if success:
                # Copy the new certificates to the target directory
                source_dir, target_dir = setup_certificate_paths(use_existing=True)
                copy_existing_certificates(source_dir, target_dir)
            else:
                print("Failed to create self-signed certificates. Please check permissions and try again.")
                exit(1)
        else:
            # Original certificate generation code (Let's Encrypt)
            _, target_dir = setup_certificate_paths(use_existing=False)
            print("Please provide an admin email for security updates with HTTPS registration")
            input_email = input("admin email [({})]: ".format(email))

            if input_email != "":
                email = input_email

            print("The system will now attempt to setup an HTTPS certificate for this server.")
            print("For this to work you must have already have purchased/acquired a domain name (or subdomain) and setup a DNS A or AAAA record to point at this server's IP address.")
            print("If you have not done this yet, please do it now...")
            time.sleep(1)
            proceed = input("Domain is ready to proceed with certificate acquisition? [(Y)/n]: ")
            if proceed == "":
                proceed = "y"
            if proceed.strip().lower()[0] != "y":
                print("Re-run this script once the domain is ready!")
                exit(1)
                
            print("Checking if port 80 is available...")
            port_check = subprocess.run(["lsof", "-i", ":80"], capture_output=True)
            if port_check.returncode == 0:
                print("\nWARNING: Port 80 is already in use. This may cause Let's Encrypt verification to fail.")
                print("The following processes are using port 80:")
                print(port_check.stdout.decode())
                print("Consider stopping these services before continuing.")
                continue_anyway = input("Continue with Let's Encrypt anyway? (y/N): ")
                if continue_anyway.lower().strip() != "y":
                    print("Aborting. Please free port 80 and try again.")
                    exit(1)

            os.system("sudo certbot certonly --standalone \
              --email {} \
              -d {} \
              --rsa-key-size 4096 \
              --agree-tos \
              --cert-name bootstrap \
              --keep-until-expiring \
              --non-interactive".format(email, domain))
              
            # Check if certbot succeeded by looking for certificates
            cert_path = "/etc/letsencrypt/live/bootstrap/fullchain.pem"
            if not os.path.exists(cert_path):
                print("\nLet's Encrypt certificate generation failed.")
                print("Would you like to use self-signed certificates instead? (Y/n)")
                use_self_signed = input("Use self-signed certificates: ")
                if use_self_signed == "" or use_self_signed.lower().strip()[0] == "y":
                    ssl_dir = "/etc/ssl/odkx"
                    ensure_directory_exists(ssl_dir)
                    success = create_self_signed_cert(domain, email, ssl_dir)
                    
                    if success:
                        # Copy the new certificates to the target directory
                        source_dir, target_dir = setup_certificate_paths(use_existing=True)
                        copy_existing_certificates(source_dir, target_dir)
                    else:
                        print("Failed to create self-signed certificates. Please check permissions and try again.")
                        exit(1)
                else:
                    print("Aborting setup. Please resolve certificate issues and try again.")
                    exit(1)
            else:
                # Copy Let's Encrypt certificates to target directory
                print("Let's Encrypt certificates generated successfully.")
                source_dir = "/etc/letsencrypt/live/bootstrap"
                target_dir = os.path.join(script_dir, "..", "certs")
                
                ensure_directory_exists(target_dir)
                try:
                    shutil.copy2(os.path.join(source_dir, "fullchain.pem"), os.path.join(target_dir, "fullchain.pem"))
                    shutil.copy2(os.path.join(source_dir, "privkey.pem"), os.path.join(target_dir, "privkey.pem"))
                    os.chmod(os.path.join(target_dir, "fullchain.pem"), 0o644)
                    os.chmod(os.path.join(target_dir, "privkey.pem"), 0o600)
                    print("Certificates copied to target directory.")
                except Exception as e:
                    print(f"Error copying Let's Encrypt certificates: {str(e)}")
                    print("You may need to manually copy the certificates later.")

        print("Attempting to save updated https configuration")
        try:
            write_to_env_file(env_file_location, domain, email)
        except Exception as e:
            print(f"Error updating https configuration: {str(e)}")
            print("You may need to manually update your https.env file.")

    return enforce_https


def replaceInFile(file_path, pattern, subst):
    try:
        fh, abs_path = mkstemp()
        with fdopen(fh,'w') as new_file:
            with open(file_path) as old_file:
                for line in old_file:
                    new_file.write(re.sub(pattern, subst, line))
        copymode(file_path, abs_path)
        remove(file_path)
        move(abs_path, file_path)
    except Exception as e:
        print(f"Error replacing text in file {file_path}: {str(e)}")
        raise

def write_to_env_file(filepath, domain_name, email):
    """A janky in-memory file write.

    This is not atomic and would use lots of ram for large files.
    """
    try:
        file_lines = []
        with open(filepath, mode="r") as f:
            for line in f:
                file_lines.append(line)

        with open(filepath, mode="w") as f:
            for line in file_lines:
                if line.startswith("HTTPS_DOMAIN="):
                    line = "HTTPS_DOMAIN={}\n".format(domain_name)
                if line.startswith("HTTPS_ADMIN_EMAIL="):
                    line = "HTTPS_ADMIN_EMAIL={}\n".format(email)
                f.write(line)
    except Exception as e:
        print(f"Error writing to env file {filepath}: {str(e)}")
        raise


def parse_env_file(filepath):
    domain = None
    email = None
    try:
        with open(filepath) as f:
            for line in f:
                if line.startswith("HTTPS_DOMAIN="):
                    domain=line[13:].strip()
                if line.startswith("HTTPS_ADMIN_EMAIL="):
                    email=line[18:].strip()
        if domain is None:
            domain = "localhost"
        if email is None:
            email = "admin@example.com"
        return (domain, email)
    except Exception as e:
        print(f"Error parsing env file {filepath}: {str(e)}")
        raise


def run_docker_builds():
    print("\nBuilding Docker images. This may take some time...")
    try:
        subprocess.run(["docker", "build", "--pull", "-t", "odk/sync-web-ui", "https://github.com/odk-x/sync-endpoint-web-ui.git"], check=True)
        subprocess.run(["docker", "build", "--pull", "-t", "odk/db-bootstrap", "db-bootstrap"], check=True)
        subprocess.run(["docker", "build", "--pull", "-t", "odk/openldap", "openldap"], check=True)
        subprocess.run(["docker", "build", "--pull", "-t", "odk/phpldapadmin", "phpldapadmin"], check=True)
        print("Docker builds completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during Docker builds: {str(e)}")
        print("You may need to fix the issues and retry.")
        retry = input("Continue with the setup anyway? (y/N): ")
        if retry.lower().strip() != "y":
            exit(1)


def run_sync_endpoint_build():
    print("\nBuilding sync endpoint. This may take some time...")
    try:
        build_cmd = "git clone -b master --single-branch --depth=1 https://github.com/odk-x/sync-endpoint && " + \
                    "cd sync-endpoint && " + \
                    "mvn -pl org.opendatakit:sync-endpoint-war,org.opendatakit:sync-endpoint-docker-swarm,org.opendatakit:sync-endpoint-common-dependencies clean install -DskipTests"
        
        subprocess.run(build_cmd, shell=True, check=True)
        print("Sync endpoint build completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during sync endpoint build: {str(e)}")
        print("You may need to fix the issues and retry.")
        retry = input("Continue with deployment anyway? (y/N): ")
        if retry.lower().strip() != "y":
            exit(1)


def deploy_stack(use_https):
    print("\nDeploying Docker stack...")
    try:
        if use_https:
            subprocess.run(["docker", "stack", "deploy", "-c", "docker-compose.yml", "-c", "docker-compose-https.yml", "syncldap"], check=True)
        else:
            subprocess.run(["docker", "stack", "deploy", "-c", "docker-compose.yml", "syncldap"], check=True)
        print("Docker stack deployed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error deploying Docker stack: {str(e)}")
        print("Deployment failed. Please check Docker logs for more information.")
        exit(1)


if __name__ == "__main__":
    print("\nODK-X Sync Endpoint Setup\n" + "="*30)
    try:
        https = run_interactive_config()
        run_docker_builds()
        run_sync_endpoint_build()
        deploy_stack(https)
        print("\nSetup completed successfully! Your ODK-X sync endpoint should now be running.")
        print("If you used self-signed certificates, you may need to configure your clients to trust them.")
    except Exception as e:
        print(f"\nAn error occurred during setup: {str(e)}")
        print("Please fix the issues and try again.")
        exit(1)
