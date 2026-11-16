# Control Hub

OMY + LEAP + Manus 장비의 모든 프로세스를 브라우저 한 화면에서 켜고, 끄고, 상태·끊긴 곳·오류·로그를 본다.
프로세스는 tmux 가 붙들고 있어서 hub 를 재시작해도 로봇은 영향받지 않는다.

```bash
pip install -e .
control-hub serve --config config/hub.fake.yaml     # 실물 없이: http://localhost:8701
cp config/hub.example.yaml config/hub.yaml
control-hub serve --config config/hub.yaml          # 실제 장비: http://localhost:8700
tmux -L shapeup attach -t hub                       # 언제든 터미널로 보기
```

명령이 바뀌면 `config/hub.yaml` 만 고치고 화면의 "설정 다시 읽기"를 누른다.

사용법, 현장 확인 항목, 설정 고치는 법: [`docs/data_preparation/control_hub_usage.md`](../docs/data_preparation/control_hub_usage.md)
