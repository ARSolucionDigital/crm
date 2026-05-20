.PHONY: up down restart logs status ps shell db-shell worker-shell backup restore clean help pull tunnel tunnel-stop

DOCKER_DIR := packages/twenty-docker
BACKUP_DIR := backups
SCRIPTS_DIR := scripts

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all containers
	cd $(DOCKER_DIR) && docker compose up -d

down: ## Stop all containers
	cd $(DOCKER_DIR) && docker compose stop

restart: ## Restart all containers
	cd $(DOCKER_DIR) && docker compose restart

pull: ## Pull latest images
	cd $(DOCKER_DIR) && docker compose pull

status: ## Show container status
	cd $(DOCKER_DIR) && docker compose ps

ps: ## Alias for status
	@$(MAKE) status

logs: ## Follow server logs
	cd $(DOCKER_DIR) && docker compose logs -f server

logs-worker: ## Follow worker logs
	cd $(DOCKER_DIR) && docker compose logs -f worker

logs-db: ## Follow database logs
	cd $(DOCKER_DIR) && docker compose logs -f db

shell: ## Open shell in server container
	cd $(DOCKER_DIR) && docker compose exec server sh

worker-shell: ## Open shell in worker container
	cd $(DOCKER_DIR) && docker compose exec worker sh

db-shell: ## Open psql shell
	cd $(DOCKER_DIR) && docker compose exec db psql -U postgres twenty

backup: ## Backup database to backups/
	@mkdir -p $(BACKUP_DIR)
	docker exec twenty-db-1 pg_dump -U postgres twenty > $(BACKUP_DIR)/twenty_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "Backup saved to $(BACKUP_DIR)/"

restore: ## Restore database from latest backup
	@if [ -z "$(BACKUP_FILE)" ]; then \
		BACKUP_FILE=$$(ls -t $(BACKUP_DIR)/*.sql 2>/dev/null | head -1); \
		if [ -z "$$BACKUP_FILE" ]; then \
			echo "No backup file found in $(BACKUP_DIR)/"; \
			exit 1; \
		fi; \
		echo "Restoring from $$BACKUP_FILE"; \
		cd $(DOCKER_DIR) && docker compose stop server worker; \
		docker exec -i twenty-db-1 psql -U postgres twenty < $$BACKUP_FILE; \
		cd $(DOCKER_DIR) && docker compose up -d; \
	else \
		echo "Restoring from $(BACKUP_FILE)"; \
		cd $(DOCKER_DIR) && docker compose stop server worker; \
		docker exec -i twenty-db-1 psql -U postgres twenty < $(BACKUP_FILE); \
		cd $(DOCKER_DIR) && docker compose up -d; \
	fi

clean: ## Stop and remove containers + volumes (DESTRUCTIVE)
	cd $(DOCKER_DIR) && docker compose down -v

tunnel: ## Start ngrok tunnel (auto-configures SERVER_URL)
	bash $(SCRIPTS_DIR)/tunnel-start.sh

tunnel-stop: ## Stop ngrok tunnel and restore localhost
	bash $(SCRIPTS_DIR)/tunnel-stop.sh
