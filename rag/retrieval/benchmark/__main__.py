"""입력 동결, 모델별 로컬 측정, 결과 집계를 실행한다."""
import argparse

from .common import models, offline_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "summarize"])
    parser.add_argument("--model", choices=[m["key"] for m in models()])
    args = parser.parse_args()
    if args.action == "prepare":
        from .prepare import download_models, freeze_inputs

        freeze_inputs()
        download_models()
        return
    offline_environment()
    if args.action == "run":
        if args.model is None:
            parser.error("run requires --model")
        from .run import run_model

        run_model(next(m for m in models() if m["key"] == args.model))
    else:
        from .summarize import summarize

        summarize()


if __name__ == "__main__":
    main()
