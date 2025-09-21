import os
import shutil
import psutil
import json
import re
import subprocess
import platform
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import threading
import time

class TerminalEmulator:
    def __init__(self):
        # Use /tmp for writable operations in production
        self.base_directory = '/tmp/terminal_workspace'
        os.makedirs(self.base_directory, exist_ok=True)
        self.current_directory = self.base_directory
        self.command_history = []
        self.aliases = {
            'll': 'ls -la',
            'la': 'ls -a',
            'clear': 'clear'
        }
        
    def execute_command(self, command):
        """Execute a command and return the result"""
        try:
            # Add to history
            if command.strip() and (not self.command_history or self.command_history[-1] != command):
                self.command_history.append(command)
                if len(self.command_history) > 1000:
                    self.command_history.pop(0)
            
            # Handle aliases
            for alias, actual_command in self.aliases.items():
                if command.startswith(alias):
                    command = command.replace(alias, actual_command, 1)
            
            # Parse command
            parts = command.strip().split()
            if not parts:
                return {"output": "", "error": "", "success": True}
            
            cmd = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            # Handle built-in commands (same as original but with restricted paths)
            if cmd == 'pwd':
                return self._pwd()
            elif cmd == 'ls':
                return self._ls(args)
            elif cmd == 'cd':
                return self._cd(args)
            elif cmd == 'mkdir':
                return self._mkdir(args)
            elif cmd == 'rm':
                return self._rm(args)
            elif cmd == 'rmdir':
                return self._rmdir(args)
            elif cmd == 'cp':
                return self._cp(args)
            elif cmd == 'mv':
                return self._mv(args)
            elif cmd == 'cat':
                return self._cat(args)
            elif cmd == 'touch':
                return self._touch(args)
            elif cmd == 'echo':
                return self._echo(args)
            elif cmd == 'history':
                return self._history()
            elif cmd == 'clear':
                return {"output": "CLEAR_SCREEN", "error": "", "success": True}
            elif cmd == 'sysinfo' or cmd == 'system':
                return self._system_info()
            elif cmd == 'ps':
                return self._process_list()
            elif cmd == 'help':
                return self._help()
            elif cmd.startswith('nl:') or cmd.startswith('natural:'):
                nl_command = command[3:] if cmd.startswith('nl:') else command[8:]
                return self._process_natural_language(nl_command)
            else:
                # Restrict system commands for security
                return {"output": "", "error": f"Command '{cmd}' not allowed in web environment. Use built-in commands or natural language.", "success": False}
                
        except Exception as e:
            return {"output": "", "error": f"Error: {str(e)}", "success": False}
    
    def _safe_path(self, path):
        """Ensure path stays within the safe directory"""
        if not path:
            return self.current_directory
        
        if os.path.isabs(path):
            # Absolute paths - restrict to base directory
            abs_path = os.path.normpath(path)
            if not abs_path.startswith(self.base_directory):
                return os.path.join(self.base_directory, os.path.basename(path))
            return abs_path
        else:
            # Relative paths
            abs_path = os.path.abspath(os.path.join(self.current_directory, path))
            if not abs_path.startswith(self.base_directory):
                return self.base_directory
            return abs_path
    
    def _pwd(self):
        # Show relative path from base directory
        rel_path = os.path.relpath(self.current_directory, self.base_directory)
        if rel_path == '.':
            return {"output": "/workspace", "error": "", "success": True}
        return {"output": f"/workspace/{rel_path}", "error": "", "success": True}
    
    def _ls(self, args):
        try:
            show_hidden = '-a' in args or '-la' in args or '-al' in args
            long_format = '-l' in args or '-la' in args or '-al' in args
            
            target_dir = self.current_directory
            for arg in args:
                if not arg.startswith('-'):
                    target_dir = self._safe_path(arg)
                    break
            
            if not os.path.exists(target_dir):
                return {"output": "", "error": f"ls: {arg}: No such file or directory", "success": False}
            
            if os.path.isfile(target_dir):
                if long_format:
                    stat = os.stat(target_dir)
                    size = stat.st_size
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%b %d %H:%M')
                    return {"output": f"-rw-r--r-- 1 user user {size:>8} {mtime} {os.path.basename(target_dir)}", "error": "", "success": True}
                else:
                    return {"output": os.path.basename(target_dir), "error": "", "success": True}
            
            items = []
            try:
                for item in os.listdir(target_dir):
                    if not show_hidden and item.startswith('.'):
                        continue
                    
                    item_path = os.path.join(target_dir, item)
                    if long_format:
                        try:
                            stat = os.stat(item_path)
                            size = stat.st_size
                            mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%b %d %H:%M')
                            is_dir = os.path.isdir(item_path)
                            permissions = 'drwxr-xr-x' if is_dir else '-rw-r--r--'
                            items.append(f"{permissions} 1 user user {size:>8} {mtime} {item}")
                        except OSError:
                            items.append(f"?????????? ? ?    ?    ?            ? {item}")
                    else:
                        items.append(item + ('/' if os.path.isdir(item_path) else ''))
            except PermissionError:
                return {"output": "", "error": f"ls: Permission denied", "success": False}
            
            if long_format:
                output = '\n'.join(sorted(items))
            else:
                if items:
                    items.sort()
                    max_len = max(len(item) for item in items) if items else 0
                    cols = max(1, 80 // (max_len + 2))
                    formatted_items = []
                    for i in range(0, len(items), cols):
                        row = items[i:i+cols]
                        formatted_items.append('  '.join(item.ljust(max_len) for item in row))
                    output = '\n'.join(formatted_items)
                else:
                    output = ""
            
            return {"output": output, "error": "", "success": True}
            
        except Exception as e:
            return {"output": "", "error": f"ls: {str(e)}", "success": False}
    
    def _cd(self, args):
        if not args:
            self.current_directory = self.base_directory
            return {"output": "", "error": "", "success": True}
        
        target = args[0]
        new_path = self._safe_path(target)
        
        if not os.path.exists(new_path):
            return {"output": "", "error": f"cd: {target}: No such file or directory", "success": False}
        
        if not os.path.isdir(new_path):
            return {"output": "", "error": f"cd: {target}: Not a directory", "success": False}
        
        self.current_directory = new_path
        return {"output": "", "error": "", "success": True}
    
    # Include other methods with similar safety modifications...
    def _mkdir(self, args):
        if not args:
            return {"output": "", "error": "mkdir: missing operand", "success": False}
        
        recursive = '-p' in args
        dirs_to_create = [arg for arg in args if not arg.startswith('-')]
        
        if not dirs_to_create:
            return {"output": "", "error": "mkdir: missing operand", "success": False}
        
        errors = []
        for dir_name in dirs_to_create:
            dir_path = self._safe_path(dir_name)
            try:
                if recursive:
                    os.makedirs(dir_path, exist_ok=True)
                else:
                    os.mkdir(dir_path)
            except FileExistsError:
                errors.append(f"mkdir: {dir_name}: File exists")
            except Exception as e:
                errors.append(f"mkdir: {dir_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": False}
        return {"output": "", "error": "", "success": True}
    
    def _touch(self, args):
        if not args:
            return {"output": "", "error": "touch: missing file operand", "success": False}
        
        errors = []
        for file_name in args:
            file_path = self._safe_path(file_name)
            try:
                Path(file_path).touch()
            except Exception as e:
                errors.append(f"touch: {file_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": False}
        return {"output": "", "error": "", "success": True}
    
    def _cat(self, args):
        if not args:
            return {"output": "", "error": "cat: missing file operand", "success": False}
        
        output_lines = []
        errors = []
        
        for file_name in args:
            file_path = self._safe_path(file_name)
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    output_lines.append(content)
            except FileNotFoundError:
                errors.append(f"cat: {file_name}: No such file or directory")
            except IsADirectoryError:
                errors.append(f"cat: {file_name}: Is a directory")
            except Exception as e:
                errors.append(f"cat: {file_name}: {str(e)}")
        
        output = ''.join(output_lines) if output_lines else ""
        error = '\n'.join(errors) if errors else ""
        
        return {"output": output, "error": error, "success": len(errors) == 0}
    
    def _echo(self, args):
        return {"output": ' '.join(args), "error": "", "success": True}
    
    def _history(self):
        if not self.command_history:
            return {"output": "", "error": "", "success": True}
        
        history_with_numbers = []
        for i, cmd in enumerate(self.command_history[-50:], 1):
            history_with_numbers.append(f"{i:>4}  {cmd}")
        
        return {"output": '\n'.join(history_with_numbers), "error": "", "success": True}
    
    def _system_info(self):
        try:
            output = f"""System Information (Web Environment):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Platform: {platform.system()} {platform.release()}
Architecture: {platform.architecture()[0]}

Environment: Render Web Service
Workspace: /tmp/terminal_workspace (ephemeral)

Note: This is a sandboxed web terminal. File operations are 
restricted to the workspace directory for security.
"""
            return {"output": output, "error": "", "success": True}
        except Exception as e:
            return {"output": "", "error": f"Error getting system info: {str(e)}", "success": False}
    
    def _process_list(self):
        return {"output": "Process listing not available in web environment for security reasons.", "error": "", "success": True}
    
    def _help(self):
        help_text = """Available Commands (Web Terminal):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

File Operations:
  ls [options] [path]     List directory contents (-l for long format, -a for hidden files)
  cd [path]              Change directory (within workspace)
  pwd                    Print working directory
  mkdir [-p] <dirs>      Create directories
  touch <files>          Create empty files
  cat <files>            Display file contents
  echo <text>            Display text

System Operations:
  sysinfo / system       Show system information
  history                Show command history
  clear                  Clear screen
  help                   Show this help message

Natural Language:
  nl: <command>          Execute natural language command
  natural: <command>     Execute natural language command
  
Examples of natural language commands:
  nl: create a folder called test
  nl: show me all files in this directory
  nl: create a file called readme.txt

Note: This is a sandboxed web terminal. System commands and file 
operations outside the workspace are restricted for security.
"""
        return {"output": help_text, "error": "", "success": True}
    
    def _process_natural_language(self, nl_command):
        """Process natural language commands (simplified for web environment)"""
        nl_command = nl_command.strip().lower()
        
        # Create folder patterns
        if re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command):
            match = re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command)
            folder_name = match.group(1)
            return self._mkdir([folder_name])
        
        # Create file patterns
        if re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command):
            match = re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command)
            file_name = match.group(1)
            return self._touch([file_name])
        
        # List files patterns
        if 'show' in nl_command and 'file' in nl_command:
            return self._ls([])
        
        # System info
        if any(word in nl_command for word in ['system', 'info']):
            return self._system_info()
        
        return {
            "output": f"I didn't understand: '{nl_command}'\n\nTry commands like:\n- create a folder test\n- create a file readme.txt\n- show me files", 
            "error": "", 
            "success": False
        }
    
    def get_completions(self, partial_command):
        """Get auto-completion suggestions"""
        if not partial_command:
            return []
        
        parts = partial_command.split()
        if len(parts) == 1:
            commands = ['ls', 'cd', 'pwd', 'mkdir', 'touch', 'cat', 'echo', 
                       'history', 'clear', 'help', 'sysinfo', 'nl:', 'natural:']
            return [cmd for cmd in commands if cmd.startswith(parts[0].lower())]
        else:
            try:
                current_input = parts[-1]
                if '/' in current_input:
                    dir_part = '/'.join(current_input.split('/')[:-1])
                    file_part = current_input.split('/')[-1]
                    search_dir = self._safe_path(dir_part)
                else:
                    file_part = current_input
                    search_dir = self.current_directory
                
                if os.path.exists(search_dir):
                    matches = []
                    for item in os.listdir(search_dir):
                        if item.startswith(file_part):
                            full_path = os.path.join(search_dir, item)
                            if os.path.isdir(full_path):
                                matches.append(item + '/')
                            else:
                                matches.append(item)
                    return matches[:10]
            except:
                pass
            
            return []

# Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key-' + str(os.urandom(16).hex()))

# Configure SocketIO with proper async mode for deployment
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False)

# Global terminal instance
terminal = TerminalEmulator()

@app.route('/')
def index():
    # Serve the HTML directly since we'll include it in the same file
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Web Terminal Emulator</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <style>
        /* Include the CSS from your index.html here - truncated for brevity */
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Courier New', monospace; 
            background: linear-gradient(135deg, #0c0c0c 0%, #1a1a1a 100%); 
            color: #00ff41; 
            height: 100vh; 
            overflow: hidden; 
        }
        /* Add all your CSS styles here */
    </style>
</head>
<body>
    <!-- Include your HTML structure here -->
    <div class="terminal-container">
        <div class="terminal-header">
            <div class="terminal-title">Web Terminal Emulator</div>
        </div>
        <div class="terminal-output" id="terminalOutput">
            <div>Welcome to Web Terminal Emulator</div>
            <div>Type 'help' for commands or try natural language with 'nl:'</div>
        </div>
        <div class="terminal-input-container">
            <span class="current-path" id="currentPath">/workspace</span>
            <span class="input-prompt">$</span>
            <input type="text" class="terminal-input" id="commandInput" placeholder="Enter command...">
        </div>
    </div>
    
    <script>
        // Include your JavaScript here - simplified version
        const socket = io();
        const terminalOutput = document.getElementById('terminalOutput');
        const commandInput = document.getElementById('commandInput');
        const currentPathElement = document.getElementById('currentPath');
        
        commandInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const command = commandInput.value.trim();
                if (command) {
                    addToOutput(createCommandLine(command));
                    socket.emit('execute_command', { command });
                    commandInput.value = '';
                }
            }
        });
        
        socket.on('command_result', (result) => {
            if (result.output === 'CLEAR_SCREEN') {
                terminalOutput.innerHTML = '';
                return;
            }
            
            if (result.cwd) {
                currentPathElement.textContent = result.cwd.replace('/tmp/terminal_workspace', '/workspace') || '/workspace';
            }
            
            if (result.output) {
                const outputElement = document.createElement('div');
                outputElement.textContent = result.output;
                outputElement.style.color = '#cccccc';
                addToOutput(outputElement);
            }
            
            if (result.error) {
                const errorElement = document.createElement('div');
                errorElement.textContent = result.error;
                errorElement.style.color = '#ff6b6b';
                addToOutput(errorElement);
            }
            
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        });
        
        function createCommandLine(command) {
            const div = document.createElement('div');
            div.innerHTML = `<span style="color: #00ff41;">user@web-terminal:/workspace$</span> <span style="color: white;">${command}</span>`;
            return div;
        }
        
        function addToOutput(element) {
            terminalOutput.appendChild(element);
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
        }
        
        commandInput.focus();
    </script>
</body>
</html>
    """

@socketio.on('execute_command')
def handle_command(data):
    try:
        command = data.get('command', '')
        result = terminal.execute_command(command)
        result['cwd'] = terminal.current_directory
        emit('command_result', result)
    except Exception as e:
        emit('command_result', {
            'output': '',
            'error': f'Server error: {str(e)}',
            'success': False,
            'cwd': terminal.current_directory
        })

@socketio.on('get_completions')
def handle_completions(data):
    try:
        partial_command = data.get('partial_command', '')
        completions = terminal.get_completions(partial_command)
        emit('completions_result', {'completions': completions})
    except Exception as e:
        emit('completions_result', {'completions': []})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
