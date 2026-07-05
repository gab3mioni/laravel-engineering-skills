#!/usr/bin/env bash
#
# Detect the stack of the Laravel project in the current directory.
#
# Prints one HAS_* flag per line for every package, file, or directory found;
# absence of a flag means "not detected". Reads composer.lock / composer.json
# and package.json directly so it works before `composer install` and without
# the composer binary. Run from the project root:
#
#   bash detect-stack.sh
#
# Exit code is always 0; consumers parse the flag lines.

set -u

flag_if_composer_pkg() {
  local flag="$1" pkg="$2"
  if [ -f composer.lock ] && grep -q "\"name\": \"${pkg}\"" composer.lock; then
    echo "${flag}"
  elif [ -f composer.json ] && grep -q "\"${pkg}\"" composer.json; then
    echo "${flag}"
  fi
}

flag_if_npm_pkg() {
  local flag="$1" pkg="$2"
  if [ -f package.json ] && grep -q "\"${pkg}\"" package.json; then
    echo "${flag}"
  fi
}

flag_if_file() {
  local flag="$1" path="$2"
  [ -f "${path}" ] && echo "${flag}"
}

flag_if_dir() {
  local flag="$1" path="$2"
  [ -d "${path}" ] && echo "${flag}"
}

flag_if_composer_pkg HAS_LARAVEL_12 "laravel/framework"
flag_if_composer_pkg HAS_OCTANE laravel/octane
flag_if_composer_pkg HAS_HORIZON laravel/horizon
flag_if_composer_pkg HAS_TELESCOPE laravel/telescope
flag_if_composer_pkg HAS_PULSE laravel/pulse
flag_if_composer_pkg HAS_SANCTUM laravel/sanctum
flag_if_composer_pkg HAS_FORTIFY laravel/fortify
flag_if_composer_pkg HAS_PASSPORT laravel/passport
flag_if_composer_pkg HAS_WAYFINDER laravel/wayfinder
flag_if_composer_pkg HAS_DUSK laravel/dusk
flag_if_composer_pkg HAS_PEST pestphp/pest
flag_if_composer_pkg HAS_PINT laravel/pint
flag_if_composer_pkg HAS_LARASTAN larastan/larastan
flag_if_composer_pkg HAS_PHPSTAN phpstan/phpstan
flag_if_composer_pkg HAS_RECTOR rector/rector
flag_if_composer_pkg HAS_INERTIA_LARAVEL inertiajs/inertia-laravel
flag_if_composer_pkg HAS_SPATIE_DATA spatie/laravel-data
flag_if_composer_pkg HAS_SPATIE_PERMISSION spatie/laravel-permission
flag_if_composer_pkg HAS_SPATIE_QB spatie/laravel-query-builder
flag_if_composer_pkg HAS_LIVEWIRE livewire/livewire

flag_if_npm_pkg HAS_INERTIA_REACT "@inertiajs/react"
flag_if_npm_pkg HAS_INERTIA_VUE "@inertiajs/vue3"
flag_if_npm_pkg HAS_REACT react
flag_if_npm_pkg HAS_VUE vue
flag_if_npm_pkg HAS_TAILWIND tailwindcss
flag_if_npm_pkg HAS_ESLINT eslint
flag_if_npm_pkg HAS_VITE vite

flag_if_file HAS_TYPESCRIPT tsconfig.json
flag_if_file HAS_GITLAB_CI .gitlab-ci.yml
flag_if_file HAS_DOCKERFILE Dockerfile
flag_if_file HAS_COMPOSE docker-compose.yml
flag_if_file HAS_COMPOSE compose.yaml
flag_if_file HAS_DEV_COMPOSE docker-compose.dev.yml
flag_if_file HAS_DEPLOY_SCRIPT deploy.sh
flag_if_file HAS_ENVOY Envoy.blade.php
flag_if_file HAS_PINT_CONFIG pint.json
flag_if_file HAS_PHPSTAN_CONFIG phpstan.neon
flag_if_file HAS_PHPSTAN_CONFIG phpstan.neon.dist
flag_if_file HAS_RECTOR_CONFIG rector.php

flag_if_dir HAS_GH_ACTIONS .github/workflows
flag_if_dir HAS_VENDOR vendor

exit 0
