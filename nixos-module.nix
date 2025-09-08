{ config, lib, pkgs, ... }:

let
  cfg = config.services.systemctl-dashboard;
  
  systemctl-dashboard = pkgs.stdenv.mkDerivation rec {
    pname = "systemctl-dashboard";
    version = "0.1.0";

    src = ./.;

    buildInputs = [ pkgs.python3 ];

    installPhase = ''
      mkdir -p $out/bin
      mkdir -p $out/share/systemctl-dashboard/templates
      
      cp dashboard.py $out/bin/systemctl-dashboard
      cp templates/index.html $out/share/systemctl-dashboard/templates/
      
      chmod +x $out/bin/systemctl-dashboard
      
      # Update the template path in the script
      substituteInPlace $out/bin/systemctl-dashboard \
        --replace 'Path(__file__).parent / "templates" / "index.html"' \
                  '"${placeholder "out"}/share/systemctl-dashboard/templates/index.html"'
    '';

    meta = with pkgs.lib; {
      description = "A web interface for managing systemd services";
      license = licenses.mit;
      maintainers = [ ];
      platforms = platforms.linux;
    };
  };
in
{
  options.services.systemctl-dashboard = {
    enable = lib.mkEnableOption "systemctl dashboard web interface";

    package = lib.mkOption {
      type = lib.types.package;
      default = systemctl-dashboard;
      description = "The systemctl-dashboard package to use";
    };

    port = lib.mkOption {
      type = lib.types.int;
      default = 8080;
      description = "Port to run the dashboard on";
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Host to bind the dashboard to";
    };

    configDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/systemctl-dashboard";
      description = "Directory to store dashboard configuration and database";
    };

    baseUrl = lib.mkOption {
      type = lib.types.str;
      default = "/";
      description = "Base URL path for the dashboard";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "systemctl-dashboard";
      description = "User to run the dashboard service as";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "systemctl-dashboard";
      description = "Group to run the dashboard service as";
    };

    extraArgs = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [];
      description = "Additional arguments to pass to systemctl-dashboard";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open firewall port for the dashboard";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      home = cfg.configDir;
      createHome = true;
    };

    users.groups.${cfg.group} = {};

    systemd.services.systemctl-dashboard = {
      description = "Systemctl Dashboard Web Interface";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.configDir;
        ExecStart = "${cfg.package}/bin/systemctl-dashboard --port ${toString cfg.port} --host ${cfg.host} --config-dir ${cfg.configDir} --base-url ${cfg.baseUrl} ${lib.concatStringsSep " " cfg.extraArgs}";
        Restart = "always";
        RestartSec = "10";
        
        # Security settings
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.configDir ];
        
        # Allow access to systemd journal
        SupplementaryGroups = [ "systemd-journal" ];
      };

      environment = {
        PYTHONPATH = "${cfg.package}/lib/python*/site-packages";
      };
    };

    # Grant sudo permissions for systemctl operations
    security.sudo.extraRules = [{
      users = [ cfg.user ];
      commands = [{
        command = "${pkgs.systemd}/bin/systemctl";
        options = [ "NOPASSWD" ];
      }];
    }];

    # Open firewall if requested
    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}