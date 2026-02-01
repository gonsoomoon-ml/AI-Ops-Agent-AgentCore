#!/usr/bin/env python
"""OpsAgent CLI Chat Interface.

대화형 CLI 인터페이스로 OpsAgent와 상호작용.

사용법:
    uv run python -m ops_agent.main
    uv run ops-agent  # pyproject.toml entry point

명령어:
    /help    - 도움말 표시
    /clear   - 화면 정리
    /exit    - 종료
    /quit    - 종료
"""

import os

from ops_agent.agent import OpsAgent
from ops_agent.config import get_settings


class Colors:
    """콘솔 출력용 컬러 코드."""

    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def print_banner() -> None:
    """시작 배너 출력."""
    print()
    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║                                                           ║")
    print("║     ██████╗ ██████╗ ███████╗ █████╗  ██████╗ ███████╗    ║")
    print("║    ██╔═══██╗██╔══██╗██╔════╝██╔══██╗██╔════╝ ██╔════╝    ║")
    print("║    ██║   ██║██████╔╝███████╗███████║██║  ███╗█████╗      ║")
    print("║    ██║   ██║██╔═══╝ ╚════██║██╔══██║██║   ██║██╔══╝      ║")
    print("║    ╚██████╔╝██║     ███████║██║  ██║╚██████╔╝███████╗    ║")
    print("║     ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ║")
    print("║                                                           ║")
    print("║          AI-Powered Operations Agent                      ║")
    print("║                                                           ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}")


def print_help() -> None:
    """도움말 출력."""
    print()
    print(f"{Colors.CYAN}{'─' * 60}{Colors.END}")
    print(f"{Colors.BOLD}OpsAgent 도움말{Colors.END}")
    print(f"{Colors.CYAN}{'─' * 60}{Colors.END}")
    print()
    print(f"{Colors.BOLD}사용 가능한 명령어:{Colors.END}")
    print(f"  {Colors.GREEN}/help{Colors.END}    - 이 도움말 표시")
    print(f"  {Colors.GREEN}/clear{Colors.END}   - 화면 정리")
    print(f"  {Colors.GREEN}/exit{Colors.END}    - 종료")
    print(f"  {Colors.GREEN}/quit{Colors.END}    - 종료")
    print()
    print(f"{Colors.BOLD}예시 질문:{Colors.END}")
    print(f"  • payment-service에서 500 에러 로그 보여줘")
    print(f"  • order-service의 최근 1시간 에러 분석해줘")
    print(f"  • Lambda 함수에서 timeout 에러 찾아줘")
    print()
    print(f"{Colors.CYAN}{'─' * 60}{Colors.END}")
    print()


def print_settings() -> None:
    """현재 설정 출력."""
    settings = get_settings()
    print()
    print(f"{Colors.DIM}설정:{Colors.END}")
    print(f"{Colors.DIM}  Model: {settings.bedrock_model_id}{Colors.END}")
    print(f"{Colors.DIM}  Region: {settings.aws_region}{Colors.END}")
    print(f"{Colors.DIM}  Language: {settings.agent_language}{Colors.END}")
    print(f"{Colors.DIM}  CloudWatch Mock: {settings.is_cloudwatch_mock}{Colors.END}")
    print()


def clear_screen() -> None:
    """화면 정리."""
    os.system("cls" if os.name == "nt" else "clear")


def chat() -> None:
    """대화형 채팅 루프."""
    print_banner()
    print_settings()

    print(f"{Colors.DIM}'/help' 입력으로 도움말을 볼 수 있습니다.{Colors.END}")
    print(f"{Colors.DIM}'/exit' 또는 '/quit'으로 종료합니다.{Colors.END}")
    print()

    # OpsAgent 초기화
    agent = OpsAgent()

    while True:
        try:
            # 사용자 입력
            print(f"{Colors.GREEN}{Colors.BOLD}You:{Colors.END} ", end="")
            user_input = input().strip()

            # 빈 입력 무시
            if not user_input:
                continue

            # 명령어 처리
            if user_input.startswith("/"):
                command = user_input.lower()

                if command in ("/exit", "/quit", "/q"):
                    print()
                    print(f"{Colors.CYAN}안녕히 가세요! 👋{Colors.END}")
                    print()
                    break

                elif command == "/help":
                    print_help()
                    continue

                elif command == "/clear":
                    clear_screen()
                    print_banner()
                    continue

                else:
                    print(f"{Colors.YELLOW}알 수 없는 명령어: {user_input}{Colors.END}")
                    print(f"{Colors.DIM}'/help'로 사용 가능한 명령어를 확인하세요.{Colors.END}")
                    print()
                    continue

            # OpsAgent 실행
            print()
            print(f"{Colors.BLUE}{Colors.BOLD}OpsAgent:{Colors.END}")
            print()

            response = agent.invoke(user_input)

            # 응답 출력
            print(f"{Colors.CYAN}{'─' * 60}{Colors.END}")
            print(response)
            print(f"{Colors.CYAN}{'─' * 60}{Colors.END}")
            print()

        except KeyboardInterrupt:
            print()
            print()
            print(f"{Colors.CYAN}Ctrl+C 감지. 종료합니다...{Colors.END}")
            print()
            break

        except EOFError:
            # 입력 스트림 종료 (파이프 또는 리다이렉션)
            print()
            break

        except Exception as e:
            print()
            print(f"{Colors.RED}오류 발생: {e}{Colors.END}")
            print()


def main() -> None:
    """메인 엔트리 포인트."""
    chat()


if __name__ == "__main__":
    main()
