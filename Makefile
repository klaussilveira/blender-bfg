.PHONY: help setup format test check build check-deps
.DEFAULT_GOAL := help
NAME := blender-bfg
VERSION := $(shell git show -s --format=%h)

help: # Display the application manual
	@echo "$(NAME) version \033[33m$(VERSION)\n\e[0m"
	@echo "\033[1;37mUSAGE\e[0m"
	@echo "  \e[4mmake\e[0m <command> [<arg1>] ... [<argN>]\n"
	@echo "\033[1;37mAVAILABLE COMMANDS\e[0m"
	@grep -E '^[a-zA-Z_-]+:.*?# .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?# "}; {printf "  \033[32m%-20s\033[0m %s\n", $$1, $$2}'

setup: check-deps # Setup dependencies and development configuration
	uv install

format: # Run code style autoformatter
	uv tool run ruff format src/

test: # Run automated test suite
	vendor/bin/phpunit

check: # Check coding style
	uv tool run ruff check src/

build: check # Build the plugin
	cd src && zip -r ../blender-bfg.zip blender_bfg/

check-deps:
	@if ! [ -x "$$(command -v uv)" ]; then\
	  echo '\n\033[0;31muv is not installed.';\
	  exit 1;\
	else\
	  echo "\033[0;32muv installed\033[0m";\
	fi
