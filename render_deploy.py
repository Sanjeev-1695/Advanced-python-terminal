#!/usr/bin/env python3
"""
Production-ready version of Advanced Terminal Emulator for Render deployment
Maintains the original beautiful interface design
"""

import os
import shutil
import json
import re
import platform
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify
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
            
            # Handle built-in commands
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
    
    def _rm(self, args):
        if not args:
            return {"output": "", "error": "rm: missing operand", "success": False}
        
        recursive = '-r' in args or '-rf' in args
        force = '-f' in args or '-rf' in args
        files_to_remove = [arg for arg in args if not arg.startswith('-')]
        
        if not files_to_remove:
            return {"output": "", "error": "rm: missing operand", "success": False}
        
        errors = []
        for file_name in files_to_remove:
            file_path = self._safe_path(file_name)
            try:
                if os.path.isdir(file_path):
                    if recursive:
                        shutil.rmtree(file_path)
                    else:
                        errors.append(f"rm: {file_name}: is a directory")
                else:
                    os.remove(file_path)
            except FileNotFoundError:
                if not force:
                    errors.append(f"rm: {file_name}: No such file or directory")
            except Exception as e:
                errors.append(f"rm: {file_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(files_to_remove)}
        return {"output": "", "error": "", "success": True}
    
    def _rmdir(self, args):
        if not args:
            return {"output": "", "error": "rmdir: missing operand", "success": False}
        
        errors = []
        for dir_name in args:
            dir_path = self._safe_path(dir_name)
            try:
                os.rmdir(dir_path)
            except OSError as e:
                errors.append(f"rmdir: {dir_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": False}
        return {"output": "", "error": "", "success": True}
    
    def _cp(self, args):
        if len(args) < 2:
            return {"output": "", "error": "cp: missing file operand", "success": False}
        
        recursive = '-r' in args
        source_files = [arg for arg in args[:-1] if not arg.startswith('-')]
        dest = args[-1]
        
        if not source_files:
            return {"output": "", "error": "cp: missing file operand", "success": False}
        
        dest_path = self._safe_path(dest)
        errors = []
        
        for source in source_files:
            source_path = self._safe_path(source)
            try:
                if os.path.isdir(source_path):
                    if recursive:
                        if os.path.isdir(dest_path):
                            shutil.copytree(source_path, os.path.join(dest_path, os.path.basename(source_path)))
                        else:
                            shutil.copytree(source_path, dest_path)
                    else:
                        errors.append(f"cp: {source}: is a directory (not copied)")
                else:
                    if os.path.isdir(dest_path):
                        shutil.copy2(source_path, dest_path)
                    else:
                        shutil.copy2(source_path, dest_path)
            except Exception as e:
                errors.append(f"cp: {source}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(source_files)}
        return {"output": "", "error": "", "success": True}
    
    def _mv(self, args):
        if len(args) < 2:
            return {"output": "", "error": "mv: missing file operand", "success": False}
        
        source_files = args[:-1]
        dest = args[-1]
        dest_path = self._safe_path(dest)
        errors = []
        
        for source in source_files:
            source_path = self._safe_path(source)
            try:
                if os.path.isdir(dest_path):
                    shutil.move(source_path, os.path.join(dest_path, os.path.basename(source_path)))
                else:
                    shutil.move(source_path, dest_path)
            except Exception as e:
                errors.append(f"mv: {source}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(source_files)}
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
            # Basic system info for web environment - FIXED: Removed Unicode characters
            output = f"""System Information (Web Environment):
================================================
Platform: {platform.system()} {platform.release()}
Architecture: {platform.architecture()[0]}

Environment: Render Web Service
Workspace: /tmp/terminal_workspace (ephemeral)
Python Version: {platform.python_version()}

Boot Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: This is a sandboxed web terminal. File operations are 
restricted to the workspace directory for security.
"""
            return {"output": output, "error": "", "success": True}
        except Exception as e:
            return {"output": "", "error": f"Error getting system info: {str(e)}", "success": False}
    
    def _process_list(self):
        return {"output": "Process listing restricted in web environment for security.", "error": "", "success": True}
    
    def _help(self):
        # FIXED: Removed Unicode characters and replaced with ASCII equivalents
        help_text = """Available Commands (Web Terminal):
================================================

File Operations:
  ls [options] [path]     List directory contents (-l for long format, -a for hidden files)
  cd [path]              Change directory (within workspace)
  pwd                    Print working directory
  mkdir [-p] <dirs>      Create directories (-p for recursive)
  rm [-rf] <files>       Remove files/directories (-r recursive, -f force)
  rmdir <dirs>           Remove empty directories
  cp [-r] <src> <dest>   Copy files/directories (-r for recursive)
  mv <src> <dest>        Move/rename files/directories
  cat <files>            Display file contents
  touch <files>          Create empty files or update timestamps
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
  nl: move file.txt to the documents folder
  nl: show me all files in this directory
  nl: delete temp.txt

Aliases:
  ll                     ls -la
  la                     ls -a

Note: This is a sandboxed web terminal. System commands and file 
operations outside the workspace are restricted for security.
"""
        return {"output": help_text, "error": "", "success": True}
    
    def _process_natural_language(self, nl_command):
        """Process natural language commands"""
        nl_command = nl_command.strip().lower()
        
        # Create folder patterns
        if re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command):
            match = re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command)
            folder_name = match.group(1)
            return self._mkdir([folder_name])
        
        if re.search(r'(?:make|create)\s+(?:a\s+)?(?:folder|directory|dir)\s+(\w+)', nl_command):
            match = re.search(r'(?:make|create)\s+(?:a\s+)?(?:folder|directory|dir)\s+(\w+)', nl_command)
            folder_name = match.group(1)
            return self._mkdir([folder_name])
        
        # Move file patterns
        if re.search(r'move\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command):
            match = re.search(r'move\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command)
            source, dest = match.groups()
            return self._mv([source, dest])
        
        # Copy file patterns
        if re.search(r'copy\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command):
            match = re.search(r'copy\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command)
            source, dest = match.groups()
            return self._cp([source, dest])
        
        # Delete file patterns
        if re.search(r'(?:delete|remove)\s+(?:file\s+)?(\S+)', nl_command):
            match = re.search(r'(?:delete|remove)\s+(?:file\s+)?(\S+)', nl_command)
            file_name = match.group(1)
            return self._rm([file_name])
        
        # Create file patterns
        if re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command):
            match = re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command)
            file_name = match.group(1)
            return self._touch([file_name])
        
        # List files patterns
        if 'show' in nl_command and 'file' in nl_command:
            if 'python' in nl_command:
                try:
                    python_files = [f for f in os.listdir(self.current_directory) if f.endswith('.py')]
                    if python_files:
                        return {"output": '\n'.join(python_files), "error": "", "success": True}
                    else:
                        return {"output": "No Python files found in current directory", "error": "", "success": True}
                except Exception as e:
                    return {"output": "", "error": str(e), "success": False}
            else:
                return self._ls([])
        
        # Navigate patterns
        if re.search(r'(?:go|navigate)\s+to\s+(\S+)', nl_command):
            match = re.search(r'(?:go|navigate)\s+to\s+(\S+)', nl_command)
            directory = match.group(1)
            return self._cd([directory])
        
        # System info patterns
        if any(word in nl_command for word in ['system', 'info', 'stats', 'performance']):
            return self._system_info()
        
        return {
            "output": f"I didn't understand the command: '{nl_command}'\n\nTry commands like:\n- create a folder test\n- move file.txt to documents\n- show me files\n- delete temp.txt", 
            "error": "", 
            "success": False
        }
    
    def get_completions(self, partial_command):
        """Get auto-completion suggestions"""
        if not partial_command:
            return []
        
        parts = partial_command.split()
        if len(parts) == 1:
            commands = ['ls', 'cd', 'pwd', 'mkdir', 'rm', 'rmdir', 'cp', 'mv', 'cat', 'touch', 'echo', 
                       'history', 'clear', 'help', 'sysinfo', 'ps', 'nl:', 'natural:']
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

# HTML template with all the styling and functionality
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced Terminal Emulator</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Courier New', 'Monaco', 'Menlo', monospace;
            background: linear-gradient(135deg, #0c0c0c 0%, #1a1a1a 100%);
            color: #00ff41;
            margin: 0;
            padding: 0;
            height: 100vh;
            overflow: hidden;
        }

        .terminal-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            background: rgba(0, 0, 0, 0.95);
            border: 2px solid #333;
            box-shadow: 0 0 50px rgba(0, 255, 65, 0.3);
        }

        .terminal-header {
            background: linear-gradient(90deg, #2d2d2d 0%, #404040 100%);
            color: #fff;
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #555;
            font-size: 14px;
        }

        .terminal-title {
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .terminal-buttons {
            display: flex;
            gap: 8px;
        }

        .terminal-button {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            cursor: pointer;
            transition: all 0.2s;
        }

        .close { background: #ff5f57; }
        .minimize { background: #ffbd2e; }
        .maximize { background: #28ca42; }

        .terminal-button:hover {
            transform: scale(1.1);
            box-shadow: 0 0 10px currentColor;
        }

        .system-stats {
            font-size: 12px;
            color: #888;
        }

        .terminal-output {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: rgba(0, 0, 0, 0.8);
            font-size: 14px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .terminal-output::-webkit-scrollbar {
            width: 8px;
        }

        .terminal-output::-webkit-scrollbar-track {
            background: #1a1a1a;
        }

        .terminal-output::-webkit-scrollbar-thumb {
            background: #555;
            border-radius: 4px;
        }

        .terminal-output::-webkit-scrollbar-thumb:hover {
            background: #777;
        }

        .command-line {
            margin-bottom: 10px;
            animation: fadeIn 0.3s ease-in;
        }

        .prompt {
            color: #00ff41;
            text-shadow: 0 0 10px rgba(0, 255, 65, 0.5);
        }

        .command {
            color: #ffffff;
            margin-left: 5px;
        }

        .output {
            color: #cccccc;
            margin-left: 20px;
            white-space: pre-wrap;
        }

        .error {
            color: #ff6b6b;
            margin-left: 20px;
            white-space: pre-wrap;
        }

        .success {
            color: #51cf66;
        }

        .terminal-input-container {
            display: flex;
            align-items: center;
            padding: 15px 20px;
            background: rgba(0, 0, 0, 0.9);
            border-top: 1px solid #333;
        }

        .current-path {
            color: #00ff41;
            margin-right: 10px;
            font-weight: bold;
            text-shadow: 0 0 5px rgba(0, 255, 65, 0.3);
        }

        .input-prompt {
            color: #00ff41;
            margin-right: 5px;
        }

        .terminal-input {
            flex: 1;
            background: transparent;
            border: none;
            color: #ffffff;
            font-family: inherit;
            font-size: 14px;
            outline: none;
            caret-color: #00ff41;
        }

        .terminal-input::placeholder {
            color: #666;
        }

        .suggestions {
            position: absolute;
            bottom: 70px;
            left: 20px;
            right: 20px;
            background: rgba(0, 0, 0, 0.95);
            border: 1px solid #333;
            border-radius: 4px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            display: none;
        }

        .suggestion-item {
            padding: 8px 12px;
            cursor: pointer;
            color: #ccc;
            border-bottom: 1px solid #222;
        }

        .suggestion-item:hover,
        .suggestion-item.selected {
            background: rgba(0, 255, 65, 0.1);
            color: #00ff41;
        }

        .typing-indicator {
            color: #00ff41;
            animation: blink 1s infinite;
        }

        @keyframes blink {
            0%, 50% { opacity: 1; }
            51%, 100% { opacity: 0; }
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .help-panel {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 0, 0, 0.95);
            border: 2px solid #333;
            border-radius: 8px;
            padding: 20px;
            width: 80%;
            max-width: 600px;
            max-height: 80%;
            overflow-y: auto;
            z-index: 2000;
            display: none;
            box-shadow: 0 0 50px rgba(0, 255, 65, 0.3);
        }

        .help-header {
            color: #00ff41;
            font-size: 18px;
            margin-bottom: 15px;
            text-align: center;
            border-bottom: 1px solid #333;
            padding-bottom: 10px;
        }

        .help-content {
            color: #ccc;
            line-height: 1.6;
        }

        .help-content h3 {
            color: #00ff41;
            margin: 15px 0 10px 0;
        }

        .help-content ul {
            margin: 10px 0 10px 20px;
        }

        .help-content li {
            margin: 5px 0;
        }

        .close-help {
            position: absolute;
            top: 10px;
            right: 15px;
            color: #ff5f57;
            cursor: pointer;
            font-size: 20px;
            font-weight: bold;
        }

        .close-help:hover {
            color: #ff8a80;
        }

        .status-bar {
            padding: 5px 20px;
            background: rgba(0, 0, 0, 0.8);
            border-top: 1px solid #333;
            font-size: 12px;
            color: #666;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .status-left {
            display: flex;
            gap: 20px;
        }

        .natural-language-hint {
            background: rgba(0, 255, 65, 0.1);
            border: 1px solid rgba(0, 255, 65, 0.3);
            border-radius: 4px;
            padding: 10px;
            margin: 10px 0;
            color: #00ff41;
            font-size: 12px;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { opacity: 0.7; }
            50% { opacity: 1; }
            100% { opacity: 0.7; }
        }

        .matrix-bg {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: -1;
            opacity: 0.1;
        }
    </style>
</head>
<body>
    <canvas class="matrix-bg" id="matrix"></canvas>
    
    <div class="terminal-container">
        <div class="terminal-header">
            <div class="terminal-title">
                <span>Terminal Emulator</span>
            </div>
            <div class="system-stats" id="systemStats">
                <span id="cpuUsage">Web Terminal</span> | 
                <span id="memUsage">Render Cloud</span> | 
                <span id="currentTime"></span>
            </div>
            <div class="terminal-buttons">
                <div class="terminal-button close" onclick="closeTerminal()"></div>
                <div class="terminal-button minimize" onclick="minimizeTerminal()"></div>
                <div class="terminal-button maximize" onclick="toggleHelp()"></div>
            </div>
        </div>

        <div class="terminal-output" id="terminalOutput">
            <div class="natural-language-hint">
                Try natural language commands! Type "nl: create a folder test" or "natural: show me files"
            </div>
            <div class="command-line">
                <span class="prompt">user@web-terminal:/workspace$</span>
                <span class="command">Welcome to Advanced Terminal Emulator</span>
            </div>
            <div class="output">Type 'help' for available commands or use natural language with 'nl:' prefix</div>
        </div>

        <div class="suggestions" id="suggestions"></div>

        <div class="terminal-input-container">
            <span class="current-path" id="currentPath">/workspace</span>
            <span class="input-prompt">$</span>
            <input type="text" class="terminal-input" id="commandInput" 
                   placeholder="Enter command... (try 'nl: create folder test')" 
                   autocomplete="off" spellcheck="false">
        </div>

        <div class="status-bar">
            <div class="status-left">
                <span>Press F1 for help</span>
                <span>Tab for autocomplete</span>
                <span>Up/Down for history</span>
            </div>
            <div class="status-right">
                <span id="connectionStatus">Connected</span>
            </div>
        </div>
    </div>

    <div class="help-panel" id="helpPanel">
        <div class="close-help" onclick="toggleHelp()">&times;</div>
        <div class="help-header">Terminal Emulator Help</div>
        <div class="help-content">
            <h3>Basic File Operations:</h3>
            <ul>
                <li><strong>ls [options] [path]</strong> - List directory contents</li>
                <li><strong>cd [path]</strong> - Change directory</li>
                <li><strong>pwd</strong> - Print working directory</li>
                <li><strong>mkdir [-p] &lt;dirs&gt;</strong> - Create directories</li>
                <li><strong>rm [-rf] &lt;files&gt;</strong> - Remove files/directories</li>
                <li><strong>cp [-r] &lt;src&gt; &lt;dest&gt;</strong> - Copy files/directories</li>
                <li><strong>mv &lt;src&gt; &lt;dest&gt;</strong> - Move/rename files</li>
                <li><strong>cat &lt;files&gt;</strong> - Display file contents</li>
                <li><strong>touch &lt;files&gt;</strong> - Create empty files</li>
            </ul>

            <h3>System Commands:</h3>
            <ul>
                <li><strong>sysinfo / system</strong> - Show system information</li>
                <li><strong>history</strong> - Show command history</li>
                <li><strong>clear</strong> - Clear screen</li>
            </ul>

            <h3>Natural Language Commands:</h3>
            <ul>
                <li><strong>nl: create a folder called test</strong></li>
                <li><strong>nl: move file.txt to documents</strong></li>
                <li><strong>nl: show me files</strong></li>
                <li><strong>nl: delete temp.txt</strong></li>
                <li><strong>nl: go to home directory</strong></li>
            </ul>

            <h3>Keyboard Shortcuts:</h3>
            <ul>
                <li><strong>Tab</strong> - Auto-complete commands and paths</li>
                <li><strong>Up / Down</strong> - Navigate command history</li>
                <li><strong>F1</strong> - Toggle this help panel</li>
            </ul>
        </div>
    </div>

    <script>
        class TerminalEmulator {
            constructor() {
                this.socket = io();
                this.commandHistory = [];
                this.historyIndex = -1;
                this.currentPath = '/workspace';
                this.suggestions = [];
                this.selectedSuggestion = -1;
                
                this.initializeElements();
                this.setupEventListeners();
                this.setupSocketHandlers();
                this.updateSystemStats();
                this.initMatrixBackground();
                
                this.commandInput.focus();
            }
            
            initializeElements() {
                this.terminalOutput = document.getElementById('terminalOutput');
                this.commandInput = document.getElementById('commandInput');
                this.currentPathElement = document.getElementById('currentPath');
                this.suggestionsElement = document.getElementById('suggestions');
                this.helpPanel = document.getElementById('helpPanel');
            }
            
            setupEventListeners() {
                this.commandInput.addEventListener('keydown', (e) => this.handleKeyDown(e));
                this.commandInput.addEventListener('input', (e) => this.handleInput(e));
                
                window.addEventListener('keydown', (e) => {
                    if (e.key === 'F1') {
                        e.preventDefault();
                        this.toggleHelp();
                    }
                });
                
                document.addEventListener('click', (e) => {
                    if (!this.suggestionsElement.contains(e.target)) {
                        this.hideSuggestions();
                    }
                });
            }
            
            setupSocketHandlers() {
                this.socket.on('connect', () => {
                    this.updateConnectionStatus(true);
                });
                
                this.socket.on('disconnect', () => {
                    this.updateConnectionStatus(false);
                });
                
                this.socket.on('command_result', (result) => {
                    this.displayCommandResult(result);
                });
                
                this.socket.on('completions_result', (data) => {
                    this.displaySuggestions(data.completions);
                });
                
                this.socket.on('history_result', (data) => {
                    this.commandHistory = data.history;
                });
            }
            
            handleKeyDown(e) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        if (this.selectedSuggestion >= 0 && this.suggestions.length > 0) {
                            this.applySuggestion(this.suggestions[this.selectedSuggestion]);
                        } else {
                            this.executeCommand();
                        }
                        break;
                        
                    case 'Tab':
                        e.preventDefault();
                        this.requestAutoComplete();
                        break;
                        
                    case 'ArrowUp':
                        e.preventDefault();
                        if (this.suggestions.length > 0) {
                            this.navigateSuggestions(-1);
                        } else {
                            this.navigateHistory(-1);
                        }
                        break;
                        
                    case 'ArrowDown':
                        e.preventDefault();
                        if (this.suggestions.length > 0) {
                            this.navigateSuggestions(1);
                        } else {
                            this.navigateHistory(1);
                        }
                        break;
                        
                    case 'Escape':
                        this.hideSuggestions();
                        break;
                }
            }
            
            handleInput(e) {
                setTimeout(() => {
                    if (this.commandInput.value.trim()) {
                        this.requestAutoComplete();
                    } else {
                        this.hideSuggestions();
                    }
                }, 100);
            }
            
            executeCommand() {
                const command = this.commandInput.value.trim();
                if (!command) return;
                
                if (this.commandHistory.length === 0 || this.commandHistory[this.commandHistory.length - 1] !== command) {
                    this.commandHistory.push(command);
                }
                this.historyIndex = this.commandHistory.length;
                
                this.addToOutput(this.createCommandLine(command));
                
                this.commandInput.value = '';
                this.hideSuggestions();
                
                if (command.toLowerCase() === 'clear') {
                    this.clearScreen();
                } else {
                    this.socket.emit('execute_command', { command });
                }
            }
            
            displayCommandResult(result) {
                if (result.output === 'CLEAR_SCREEN') {
                    this.clearScreen();
                    return;
                }
                
                if (result.cwd) {
                    this.currentPath = result.cwd.replace('/tmp/terminal_workspace', '/workspace') || '/workspace';
                    this.currentPathElement.textContent = this.getShortPath(this.currentPath);
                }
                
                if (result.output) {
                    const outputElement = document.createElement('div');
                    outputElement.className = 'output';
                    outputElement.textContent = result.output;
                    this.addToOutput(outputElement);
                }
                
                if (result.error) {
                    const errorElement = document.createElement('div');
                    errorElement.className = 'error';
                    errorElement.textContent = result.error;
                    this.addToOutput(errorElement);
                }
                
                this.scrollToBottom();
            }
            
            createCommandLine(command) {
                const commandLineElement = document.createElement('div');
                commandLineElement.className = 'command-line';
                
                const promptElement = document.createElement('span');
                promptElement.className = 'prompt';
                promptElement.textContent = `user@web-terminal:${this.getShortPath(this.currentPath)}#!/usr/bin/env python3
"""
Production-ready version of Advanced Terminal Emulator for Render deployment
Maintains the original beautiful interface design
"""

import os
import shutil
import json
import re
import platform
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify
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
            
            # Handle built-in commands
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
    
    def _rm(self, args):
        if not args:
            return {"output": "", "error": "rm: missing operand", "success": False}
        
        recursive = '-r' in args or '-rf' in args
        force = '-f' in args or '-rf' in args
        files_to_remove = [arg for arg in args if not arg.startswith('-')]
        
        if not files_to_remove:
            return {"output": "", "error": "rm: missing operand", "success": False}
        
        errors = []
        for file_name in files_to_remove:
            file_path = self._safe_path(file_name)
            try:
                if os.path.isdir(file_path):
                    if recursive:
                        shutil.rmtree(file_path)
                    else:
                        errors.append(f"rm: {file_name}: is a directory")
                else:
                    os.remove(file_path)
            except FileNotFoundError:
                if not force:
                    errors.append(f"rm: {file_name}: No such file or directory")
            except Exception as e:
                errors.append(f"rm: {file_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(files_to_remove)}
        return {"output": "", "error": "", "success": True}
    
    def _rmdir(self, args):
        if not args:
            return {"output": "", "error": "rmdir: missing operand", "success": False}
        
        errors = []
        for dir_name in args:
            dir_path = self._safe_path(dir_name)
            try:
                os.rmdir(dir_path)
            except OSError as e:
                errors.append(f"rmdir: {dir_name}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": False}
        return {"output": "", "error": "", "success": True}
    
    def _cp(self, args):
        if len(args) < 2:
            return {"output": "", "error": "cp: missing file operand", "success": False}
        
        recursive = '-r' in args
        source_files = [arg for arg in args[:-1] if not arg.startswith('-')]
        dest = args[-1]
        
        if not source_files:
            return {"output": "", "error": "cp: missing file operand", "success": False}
        
        dest_path = self._safe_path(dest)
        errors = []
        
        for source in source_files:
            source_path = self._safe_path(source)
            try:
                if os.path.isdir(source_path):
                    if recursive:
                        if os.path.isdir(dest_path):
                            shutil.copytree(source_path, os.path.join(dest_path, os.path.basename(source_path)))
                        else:
                            shutil.copytree(source_path, dest_path)
                    else:
                        errors.append(f"cp: {source}: is a directory (not copied)")
                else:
                    if os.path.isdir(dest_path):
                        shutil.copy2(source_path, dest_path)
                    else:
                        shutil.copy2(source_path, dest_path)
            except Exception as e:
                errors.append(f"cp: {source}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(source_files)}
        return {"output": "", "error": "", "success": True}
    
    def _mv(self, args):
        if len(args) < 2:
            return {"output": "", "error": "mv: missing file operand", "success": False}
        
        source_files = args[:-1]
        dest = args[-1]
        dest_path = self._safe_path(dest)
        errors = []
        
        for source in source_files:
            source_path = self._safe_path(source)
            try:
                if os.path.isdir(dest_path):
                    shutil.move(source_path, os.path.join(dest_path, os.path.basename(source_path)))
                else:
                    shutil.move(source_path, dest_path)
            except Exception as e:
                errors.append(f"mv: {source}: {str(e)}")
        
        if errors:
            return {"output": "", "error": '\n'.join(errors), "success": len(errors) < len(source_files)}
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
            # Basic system info for web environment - FIXED: Removed Unicode characters
            output = f"""System Information (Web Environment):
================================================
Platform: {platform.system()} {platform.release()}
Architecture: {platform.architecture()[0]}

Environment: Render Web Service
Workspace: /tmp/terminal_workspace (ephemeral)
Python Version: {platform.python_version()}

Boot Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: This is a sandboxed web terminal. File operations are 
restricted to the workspace directory for security.
"""
            return {"output": output, "error": "", "success": True}
        except Exception as e:
            return {"output": "", "error": f"Error getting system info: {str(e)}", "success": False}
    
    def _process_list(self):
        return {"output": "Process listing restricted in web environment for security.", "error": "", "success": True}
    
    def _help(self):
        # FIXED: Removed Unicode characters and replaced with ASCII equivalents
        help_text = """Available Commands (Web Terminal):
================================================

File Operations:
  ls [options] [path]     List directory contents (-l for long format, -a for hidden files)
  cd [path]              Change directory (within workspace)
  pwd                    Print working directory
  mkdir [-p] <dirs>      Create directories (-p for recursive)
  rm [-rf] <files>       Remove files/directories (-r recursive, -f force)
  rmdir <dirs>           Remove empty directories
  cp [-r] <src> <dest>   Copy files/directories (-r for recursive)
  mv <src> <dest>        Move/rename files/directories
  cat <files>            Display file contents
  touch <files>          Create empty files or update timestamps
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
  nl: move file.txt to the documents folder
  nl: show me all files in this directory
  nl: delete temp.txt

Aliases:
  ll                     ls -la
  la                     ls -a

Note: This is a sandboxed web terminal. System commands and file 
operations outside the workspace are restricted for security.
"""
        return {"output": help_text, "error": "", "success": True}
    
    def _process_natural_language(self, nl_command):
        """Process natural language commands"""
        nl_command = nl_command.strip().lower()
        
        # Create folder patterns
        if re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command):
            match = re.search(r'create.*(?:folder|directory|dir).*(?:called|named)\s+(\w+)', nl_command)
            folder_name = match.group(1)
            return self._mkdir([folder_name])
        
        if re.search(r'(?:make|create)\s+(?:a\s+)?(?:folder|directory|dir)\s+(\w+)', nl_command):
            match = re.search(r'(?:make|create)\s+(?:a\s+)?(?:folder|directory|dir)\s+(\w+)', nl_command)
            folder_name = match.group(1)
            return self._mkdir([folder_name])
        
        # Move file patterns
        if re.search(r'move\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command):
            match = re.search(r'move\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command)
            source, dest = match.groups()
            return self._mv([source, dest])
        
        # Copy file patterns
        if re.search(r'copy\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command):
            match = re.search(r'copy\s+(\S+)\s+(?:to|into)\s+(?:the\s+)?(\S+)', nl_command)
            source, dest = match.groups()
            return self._cp([source, dest])
        
        # Delete file patterns
        if re.search(r'(?:delete|remove)\s+(?:file\s+)?(\S+)', nl_command):
            match = re.search(r'(?:delete|remove)\s+(?:file\s+)?(\S+)', nl_command)
            file_name = match.group(1)
            return self._rm([file_name])
        
        # Create file patterns
        if re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command):
            match = re.search(r'create.*file.*(?:called|named)\s+(\S+)', nl_command)
            file_name = match.group(1)
            return self._touch([file_name])
        
        # List files patterns
        if 'show' in nl_command and 'file' in nl_command:
            if 'python' in nl_command:
                try:
                    python_files = [f for f in os.listdir(self.current_directory) if f.endswith('.py')]
                    if python_files:
                        return {"output": '\n'.join(python_files), "error": "", "success": True}
                    else:
                        return {"output": "No Python files found in current directory", "error": "", "success": True}
                except Exception as e:
                    return {"output": "", "error": str(e), "success": False}
            else:
                return self._ls([])
        
        # Navigate patterns
        if re.search(r'(?:go|navigate)\s+to\s+(\S+)', nl_command):
            match = re.search(r'(?:go|navigate)\s+to\s+(\S+)', nl_command)
            directory = match.group(1)
            return self._cd([directory])
        
        # System info patterns
        if any(word in nl_command for word in ['system', 'info', 'stats', 'performance']):
            return self._system_info()
        
        return {
            "output": f"I didn't understand the command: '{nl_command}'\n\nTry commands like:\n- create a folder test\n- move file.txt to documents\n- show me files\n- delete temp.txt", 
            "error": "", 
            "success": False
        }
    
    def get_completions(self, partial_command):
        """Get auto-completion suggestions"""
        if not partial_command:
            return []
        
        parts = partial_command.split()
        if len(parts) == 1:
            commands = ['ls', 'cd', 'pwd', 'mkdir', 'rm', 'rmdir', 'cp', 'mv', 'cat', 'touch', 'echo', 
                       'history', 'clear', 'help', 'sysinfo', 'ps', 'nl:', 'natural:']
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

# HTML template with all the styling and functionality
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced Terminal Emulator</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.0/socket.io.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Courier New', 'Monaco', 'Menlo', monospace;
            background: linear-gradient(135deg, #0c0c0c 0%, #1a1a1a 100%);
            color: #00ff41;
            margin: 0;
            padding: 0;
            height: 100vh;
            overflow: hidden;
        }

        .terminal-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            background: rgba(0, 0, 0, 0.95);
            border: 2px solid #333;
            box-shadow: 0 0 50px rgba(0, 255, 65, 0.3);
        }

        .terminal-header {
            background: linear-gradient(90deg, #2d2d2d 0%, #404040 100%);
            color: #fff;
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #555;
            font-size: 14px;
        }

        .terminal-title {
            font-weight: bold;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .terminal-buttons {
            display: flex;
            gap: 8px;
        }

        .terminal-button {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            cursor: pointer;
            transition: all 0.2s;
        }

        .close { background: #ff5f57; }
        .minimize { background: #ffbd2e; }
        .maximize { background: #28ca42; }

        .terminal-button:hover {
            transform: scale(1.1);
            box-shadow: 0 0 10px currentColor;
        }

        .system-stats {
            font-size: 12px;
            color: #888;
        }

        .terminal-output {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: rgba(0, 0, 0, 0.8);
            font-size: 14px;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .terminal-output::-webkit-scrollbar {
            width: 8px;
        }

        .terminal-output::-webkit-scrollbar-track {
            background: #1a1a1a;
        }

        .terminal-output::-webkit-scrollbar-thumb {
            background: #555;
            border-radius: 4px;
        }

        .terminal-output::-webkit-scrollbar-thumb:hover {
            background: #777;
        }

        .command-line {
            margin-bottom: 10px;
            animation: fadeIn 0.3s ease-in;
        }

        .prompt {
            color: #00ff41;
            text-shadow: 0 0 10px rgba(0, 255, 65, 0.5);
        }

        .command {
            color: #ffffff;
            margin-left: 5px;
        }

        .output {
            color: #cccccc;
            margin-left: 20px;
            white-space: pre-wrap;
        }

        .error {
            color: #ff6b6b;
            margin-left: 20px;
            white-space: pre-wrap;
        }

        .success {
            color: #51cf66;
        }

        .terminal-input-container {
            display: flex;
            align-items: center;
            padding: 15px 20px;
            background: rgba(0, 0, 0, 0.9);
            border-top: 1px solid #333;
        }

        .current-path {
            color: #00ff41;
            margin-right: 10px;
            font-weight: bold;
            text-shadow: 0 0 5px rgba(0, 255, 65, 0.3);
        }

        .input-prompt {
            color: #00ff41;
            margin-right: 5px;
        }

        .terminal-input {
            flex: 1;
            background: transparent;
            border: none;
            color: #ffffff;
            font-family: inherit;
            font-size: 14px;
            outline: none;
            caret-color: #00ff41;
        }

        .terminal-input::placeholder {
            color: #666;
        }

;
                
                const commandElement = document.createElement('span');
                commandElement.className = 'command';
                commandElement.textContent = ' ' + command;
                
                commandLineElement.appendChild(promptElement);
                commandLineElement.appendChild(commandElement);
                
                return commandLineElement;
            }
            
            addToOutput(element) {
                this.terminalOutput.appendChild(element);
                this.scrollToBottom();
            }
            
            scrollToBottom() {
                this.terminalOutput.scrollTop = this.terminalOutput.scrollHeight;
            }
            
            clearScreen() {
                this.terminalOutput.innerHTML = `
                    <div class="natural-language-hint">
                        Try natural language commands! Type "nl: create a folder test" or "natural: show me files"
                    </div>
                `;
            }
            
            getShortPath(path) {
                if (!path) return '/workspace';
                
                if (path === '/workspace') return '/workspace';
                
                const parts = path.split('/').filter(p => p);
                if (parts.length > 2) {
                    return '.../' + parts.slice(-2).join('/');
                }
                return path;
            }
            
            requestAutoComplete() {
                const command = this.commandInput.value;
                if (command.trim()) {
                    this.socket.emit('get_completions', { partial_command: command });
                }
            }
            
            displaySuggestions(suggestions) {
                this.suggestions = suggestions;
                this.selectedSuggestion = -1;
                
                if (suggestions.length === 0) {
                    this.hideSuggestions();
                    return;
                }
                
                this.suggestionsElement.innerHTML = '';
                suggestions.forEach((suggestion, index) => {
                    const item = document.createElement('div');
                    item.className = 'suggestion-item';
                    item.textContent = suggestion;
                    item.onclick = () => this.applySuggestion(suggestion);
                    this.suggestionsElement.appendChild(item);
                });
                
                this.suggestionsElement.style.display = 'block';
            }
            
            hideSuggestions() {
                this.suggestionsElement.style.display = 'none';
                this.suggestions = [];
                this.selectedSuggestion = -1;
            }
            
            navigateSuggestions(direction) {
                if (this.suggestions.length === 0) return;
                
                const items = this.suggestionsElement.querySelectorAll('.suggestion-item');
                if (this.selectedSuggestion >= 0) {
                    items[this.selectedSuggestion].classList.remove('selected');
                }
                
                this.selectedSuggestion += direction;
                if (this.selectedSuggestion < 0) {
                    this.selectedSuggestion = this.suggestions.length - 1;
                } else if (this.selectedSuggestion >= this.suggestions.length) {
                    this.selectedSuggestion = 0;
                }
                
                items[this.selectedSuggestion].classList.add('selected');
                items[this.selectedSuggestion].scrollIntoView({ block: 'nearest' });
            }
            
            applySuggestion(suggestion) {
                const currentCommand = this.commandInput.value;
                const parts = currentCommand.split(' ');
                
                if (parts.length === 1) {
                    this.commandInput.value = suggestion + ' ';
                } else {
                    parts[parts.length - 1] = suggestion;
                    this.commandInput.value = parts.join(' ') + (suggestion.endsWith('/') ? '' : ' ');
                }
                
                this.hideSuggestions();
                this.commandInput.focus();
                this.commandInput.setSelectionRange(this.commandInput.value.length, this.commandInput.value.length);
            }
            
            navigateHistory(direction) {
                if (this.commandHistory.length === 0) return;
                
                this.historyIndex += direction;
                
                if (this.historyIndex < 0) {
                    this.historyIndex = 0;
                } else if (this.historyIndex >= this.commandHistory.length) {
                    this.historyIndex = this.commandHistory.length;
                    this.commandInput.value = '';
                    return;
                }
                
                this.commandInput.value = this.commandHistory[this.historyIndex] || '';
                
                setTimeout(() => {
                    this.commandInput.setSelectionRange(this.commandInput.value.length, this.commandInput.value.length);
                }, 0);
            }
            
            updateConnectionStatus(connected) {
                const statusElement = document.getElementById('connectionStatus');
                statusElement.textContent = connected ? 'Connected' : 'Disconnected';
                statusElement.style.color = connected ? '#51cf66' : '#ff6b6b';
            }
            
            updateSystemStats() {
                const updateTime = () => {
                    const now = new Date();
                    document.getElementById('currentTime').textContent = 
                        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                };
                
                updateTime();
                setInterval(updateTime, 1000);
            }
            
            toggleHelp() {
                const isVisible = this.helpPanel.style.display === 'block';
                this.helpPanel.style.display = isVisible ? 'none' : 'block';
                if (!isVisible) {
                    this.commandInput.blur();
                } else {
                    this.commandInput.focus();
                }
            }
            
            initMatrixBackground() {
                const canvas = document.getElementById('matrix');
                const ctx = canvas.getContext('2d');
                
                const resizeCanvas = () => {
                    canvas.width = window.innerWidth;
                    canvas.height = window.innerHeight;
                };
                
                resizeCanvas();
                
                const chars = '01';
                const fontSize = 10;
                let columns = Math.floor(canvas.width / fontSize);
                let drops = [];
                
                const resetDrops = () => {
                    columns = Math.floor(canvas.width / fontSize);
                    drops = [];
                    for (let i = 0; i < columns; i++) {
                        drops[i] = Math.random() * canvas.height / fontSize;
                    }
                };
                
                resetDrops();
                
                const draw = () => {
                    ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    
                    ctx.fillStyle = '#00ff41';
                    ctx.font = `${fontSize}px monospace`;
                    
                    for (let i = 0; i < drops.length; i++) {
                        const text = chars[Math.floor(Math.random() * chars.length)];
                        ctx.fillText(text, i * fontSize, drops[i] * fontSize);
                        
                        if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                            drops[i] = 0;
                        }
                        drops[i]++;
                    }
                };
                
                setInterval(draw, 33);
                
                window.addEventListener('resize', () => {
                    resizeCanvas();
                    resetDrops();
                });
            }
        }
        
        function closeTerminal() {
            if (confirm('Are you sure you want to close the terminal?')) {
                window.close();
            }
        }
        
        function minimizeTerminal() {
            const container = document.querySelector('.terminal-container');
            container.style.transform = 'scale(0.8)';
            container.style.opacity = '0.8';
            setTimeout(() => {
                container.style.transform = 'scale(1)';
                container.style.opacity = '1';
            }, 300);
        }
        
        function toggleHelp() {
            if (window.terminal) {
                window.terminal.toggleHelp();
            }
        }
        
        window.addEventListener('DOMContentLoaded', () => {
            window.terminal = new TerminalEmulator();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

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

@socketio.on('get_history')
def handle_history(data):
    try:
        emit('history_result', {'history': terminal.command_history})
    except Exception as e:
        emit('history_result', {'history': []})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
