#!/usr/bin/env python3
import os
import subprocess
import time
import argparse

def run_command(command, cwd=None, ignore_errors=False):
    try:
        print(f"Running: {command}")
        subprocess.check_call(command, shell=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        if not ignore_errors:
            print(f"Error running command: {e}")
            if not ignore_errors:
                 raise e
        else:
            print(f"Command failed (ignored): {e}")

def patch_file(filepath, target, replacement):
    if not os.path.exists(filepath):
        print(f"Error: File {filepath} not found.")
        return False
    
    with open(filepath, 'r') as f:
        content = f.read()
    
    if replacement in content:
        print(f"File {filepath} already patched.")
        return True

    if target not in content:
        print(f"Warning: Target string not found in {filepath}. Patch might have failed or file changed.")
        return False
        
    new_content = content.replace(target, replacement)
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    print(f"Patched {filepath}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Deploy UltimateXnova on VPS")
    parser.add_argument("--port", type=int, default=3838, help="Host port for the web application (default: 3838)")
    args = parser.parse_args()

    project_dir = os.getcwd() # Assumes script is run from project root
    print(f"Deploying UltimateXnova from {project_dir}...")

    # 1. Patch GeneralFunctions.php
    print("\n[1/5] Patching Codebase...")
    gf_path = os.path.join(project_dir, 'includes', 'GeneralFunctions.php')
    
    # Patch 1: Add error_log to exceptionHandler
    target1 = "function exceptionHandler($exception)\n{"
    replacement1 = "function exceptionHandler($exception)\n{\n\t/** @var $exception ErrorException|Exception */\n\terror_log(\"Exception: \" . $exception->getMessage() . \" in \" . $exception->getFile() . \":\" . $exception->getLine());"
    patch_file(gf_path, target1, replacement1)

    # Patch 2: Disable ticket creation during install
    target2 = "/* Debug via Support Ticket */\n\tglobal $USER;"
    replacement2 = "/* Debug via Support Ticket */\n\tif (MODE !== 'INSTALL') {\n\t\tglobal $USER;"
    # We need to close the brace too, but a simple replace might be tricky if context varies. 
    # Let's try a more robust block replace if the simple one fails or just use the one we know works from previous edit.
    
    # Actually, for the second patch, let's read the file and look for the specific block to replace accurately.
    with open(gf_path, 'r') as f:
        content = f.read()
    
    old_block = """	/* Debug via Support Ticket */
	global $USER;
	if (isset($USER)) {
		$ErrSource = $USER['id'];
		$ErrName = $USER['username'];
	} else {
		$ErrSource = 1;
		$ErrName = 'System';
	}
	require 'includes/classes/class.SupportTickets.php';
	$ticketObj	= new SupportTickets;
	$ticketID	= $ticketObj->createTicket($ErrSource, '1', $errorType[$errno]);
	$ticketObj->createAnswer($ticketID, $ErrSource, $ErrName, $errorType[$errno], $errorText, 0);
}"""
    
    new_block = """	/* Debug via Support Ticket */
	if (MODE !== 'INSTALL') {
		global $USER;
		if (isset($USER)) {
			$ErrSource = $USER['id'];
			$ErrName = $USER['username'];
		} else {
			$ErrSource = 1;
			$ErrName = 'System';
		}
		require 'includes/classes/class.SupportTickets.php';
		$ticketObj	= new SupportTickets;
		$ticketID	= $ticketObj->createTicket($ErrSource, '1', $errorType[$errno]);
		$ticketObj->createAnswer($ticketID, $ErrSource, $ErrName, $errorType[$errno], $errorText, 0);
	}
}"""

    stripped_content = content.replace(" ", "").replace("\t", "").replace("\n", "").replace("\r", "")
    stripped_new_block = new_block.replace(" ", "").replace("\t", "").replace("\n", "").replace("\r", "")

    if old_block in content:
        content = content.replace(old_block, new_block)
        with open(gf_path, 'w') as f:
            f.write(content)
        print("Patched GeneralFunctions.php (Ticket Logic)")
    elif stripped_new_block in stripped_content:
        print("GeneralFunctions.php (Ticket Logic) already patched.")
    else:
        print("Warning: Could not match block for Ticket Logic patch. Check indentation.")

    # Patch 3: Fix Config Not Found in ExceptionHandler
    print("Patching Config Class access in ExceptionHandler...")
    target3 = "if (MODE !== 'INSTALL') {\n\t\ttry {\n\t\t\t$config\t\t= Config::get();"
    replacement3 = "if (MODE !== 'INSTALL' && class_exists('Config')) {\n\t\ttry {\n\t\t\t$config\t\t= Config::get();"
    patch_file(gf_path, target3, replacement3)
    

    # 2. Configure Docker Compose
    print("\n[2/5] Configuring Docker...")
    dc_path = os.path.join(project_dir, 'docker-compose.yml')
    with open(dc_path, 'r') as f:
        dc_content = f.read()
    
    # Replace port mapping if needed
    if '3838:80' in dc_content and str(args.port) != '3838':
        dc_content = dc_content.replace('3838:80', f'{args.port}:80')
        with open(dc_path, 'w') as f:
            f.write(dc_content)
        print(f"Updated docker-compose.yml to use port {args.port}")


    # 3. Fix Permissions
    print("\n[3/5] Fixing Permissions...")
    
    # Ensure cache directory exists
    cache_path = os.path.join(project_dir, 'cache')
    if not os.path.exists(cache_path):
        print("Creating missing 'cache' directory...")
        os.makedirs(cache_path)

    try:
        run_command("chmod -R 777 includes cache", cwd=project_dir)
    except Exception:
        print("Permission change failed. Trying with sudo...")
        try:
             run_command("sudo chmod -R 777 includes cache", cwd=project_dir)
        except Exception as e:
             print(f"Warning: Could not change permissions even with sudo: {e}")
             print("You may need to manually run: sudo chmod -R 777 includes cache")
    
    install_lock_file = os.path.join(project_dir, 'includes', 'ENABLE_INSTALL_TOOL')
    if not os.path.exists(install_lock_file):
        print("Creating install tool lock file...")
        with open(install_lock_file, 'w') as f:
            pass # Create empty file
    
    # Update timestamp
    os.utime(install_lock_file, None)
    
    # Ensure config.php exists and is writable (or create empty if missing for initial check)
    # Actually, allow it to be missing so installer promptscreate. 
    # BUT, installer checks writability by touching. 
    # If we deleted config.php in verification, ensure correct state.
    # Installer step 2 checks if it can touch config.php. 
    # So we don't need to create it, just ensure parent dir is writable (done by chmod 777 includes).
    config_path = os.path.join(project_dir, 'includes', 'config.php')
    if os.path.exists(config_path):
        os.chmod(config_path, 0o777) # Ensure writable if exists


    # 4. Start Docker
    print("\n[4/5] Starting Docker Containers...")
    
    # Detect docker compose command
    docker_cmd = "docker-compose"
    try:
        subprocess.check_call("docker-compose --version", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        try:
            subprocess.check_call("docker compose version", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            docker_cmd = "docker compose"
        except:
            print("Error: neither 'docker-compose' nor 'docker compose' found. Please install Docker and Docker Compose.")
            exit(1)
            
    print(f"Using command: {docker_cmd}")
    run_command(f"{docker_cmd} down", cwd=project_dir, ignore_errors=True)
    run_command(f"{docker_cmd} up -d --build", cwd=project_dir)


    # 5. Output Nginx Config
    print("\n[5/5] Deployment Complete!")
    print("\n" + "="*50)
    print("Nginx Configuration Snippet")
    print("="*50)
    print(f"""
server {{
    listen 80;
    server_name YOUR_DOMAIN.com;

    location / {{
        proxy_pass http://127.0.0.1:{args.port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
""")
    print("="*50)
    print("\nTo start installation, visit: http://YOUR_VPS_IP:" + str(args.port) + "/install/")
    print(f"Allow port {args.port} in your firewall if accessing directly, or use the Nginx config above.")

if __name__ == "__main__":
    main()
