# Systemctl Dashboard

Web interface for monitoring and controlling systemd services.

## Usage

```bash
./dashboard.py --port 8080 --config-dir ~/.config/systemctl-dashboard --base-url /health/
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--port` | 5000 | Port to run on |
| `--host` | 127.0.0.1 | Host to bind to |
| `--config-dir` | . | Directory for config files |
| `--base-url` | / | Base URL path |

## Dependencies

- Python 3.11+
- Standard library only

## Development

Use devbox for consistent environment:

```bash
# Auto load devbox shell whenver you enter the directory
direnv allow

# Launch
./dashboard.py --port 8080
```

## Nix Deployment

### Direct Run

```bash
nix run github:your-username/systemctl-dashboard
```

### Build Package

```bash
nix build github:your-username/systemctl-dashboard
./result/bin/systemctl-dashboard --port 8080
```

### NixOS Service

Add to `configuration.nix`:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systemctl-dashboard.url = "github:your-username/systemctl-dashboard";
  };

  outputs = { nixpkgs, systemctl-dashboard, ... }: {
    nixosConfigurations.your-host = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        systemctl-dashboard.nixosModules.default
        {
          services.systemctl-dashboard = {
            enable = true;
            port = 8080;
            host = "0.0.0.0";
            openFirewall = true;
          };
        }
      ];
    };
  };
}
```

### Standalone Module

Copy `nixos-module.nix` to your configuration:

```nix
{ config, pkgs, ... }:
{
  imports = [ ./nixos-module.nix ];
  
  services.systemctl-dashboard = {
    enable = true;
    port = 8080;
    host = "127.0.0.1";
    configDir = "/var/lib/systemctl-dashboard";
    baseUrl = "/dashboard/";
    openFirewall = false;
  };
}
```

#### Nix Service Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enable` | bool | false | Enable service |
| `port` | int | 8080 | Port to run on |
| `host` | string | 127.0.0.1 | Host to bind to |
| `configDir` | string | /var/lib/systemctl-dashboard | Config directory |
| `baseUrl` | string | / | Base URL path |
| `user` | string | systemctl-dashboard | Service user |
| `group` | string | systemctl-dashboard | Service group |
| `extraArgs` | list | [] | Additional CLI arguments |
| `openFirewall` | bool | false | Open firewall port |

