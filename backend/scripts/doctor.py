"""Read-only local readiness report. Never prints credentials or calls external services."""
import importlib.util
import shutil

from backend.app.shared.settings import get_settings


def main():
    settings = get_settings()
    print(f"Mode: {settings.app_mode}")
    for binary in ["node", "npm", "docker"]:
        print(f"{binary}: {'available' if shutil.which(binary) else 'not found on PATH'}")
    for module in ["fastapi", "psycopg", "playwright", "huggingface_hub"]:
        print(f"{module}: {'installed' if importlib.util.find_spec(module) else 'missing'}")
    print(f"Hugging Face credentials/model/provider: {'configured' if settings.hf_token.get_secret_value() and settings.hf_model_id and settings.hf_provider else 'not configured'}")
    print(f"Neon connection: {'configured' if settings.database_url.get_secret_value() else 'not configured'}")
    print(f"Positive inference budget: {'configured' if settings.experiment_budget_limit > 0 else 'not configured'}")
    print("Configured is not verified: this report does not test live services.")
    print("Required experiment: 500 executed mandatory trials per version; 10 featured characters.")


if __name__ == "__main__":
    main()
