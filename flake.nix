{
  description ="cookidump - dumps cookidoo recipes";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:nixos/nixpkgs";
  };

  outputs = { self, nixpkgs, flake-utils}:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pname = "cookidump";

        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
            allowUnfreePredicate = pkg: builtins.elem (pkgs.lib.getName pkg) [
              "google-chrome-stable"
            ];
            # well... google-chrome is only for x86_64-linux
            allowBroken = true;
            allowUnsupportedSystem = true;
          };
        };

        cookidumpPy = pkgs.copyPathToStore ./cookidump.py;

        pyEnv = pkgs.python3.withPackages (pyPkgs: with pyPkgs; [
          selenium
          beautifulsoup4
        ]);

        runtimeDeps = with pkgs; [ pyEnv google-chrome chromedriver ];

      in {
        packages = {
          ${pname} = pkgs.writeShellApplication {
            name = pname;

            runtimeInputs = runtimeDeps;

            text = with pkgs; ''
              export GOOGLE_CHROME_PATH=${google-chrome}/bin/google-chrome-stable
              python ${cookidumpPy} ${chromedriver}/bin/chromedriver "$@"
            '';
          };

          default = self.packages.${system}.${pname};
        };

        devShells.default = with pkgs; mkShell {
          GOOGLE_CHROME_PATH="${google-chrome}/bin/google-chrome-stable";
          buildInputs = runtimeDeps;
        };
      }


    );

}
