# [AeroclubChallenge2023](https://codenrock.com/contests/aeroclub-challenge-2023#/)

Участие в хакатоне Aeroclub Challenge 2023 от компании «Аэроклуб» на сайте [Codenrock](https://codenrock.com/) в треке №2 "Создание сервиса ранжирования предложений Auto Avia Offer" (Автоматизация процесса подбора и отправки вариантов перелета с ценами в ответ на заявку по электронной почте). Занял 7 место.

В файле Solution.ipynb описано основеное решение. Если не удаётся посмотреть в github, то можно глянуть [тут](https://nbviewer.org/github/ilkaxd/AeroclubChallenge2023/blob/main/Solution.ipynb).

Если хотим использовать модель градиентного бустинга, то запускаем файл:

`python -m venv venv`

`venv/Scripts/activate`

`pip install -r requirements.py`

`python use_models.py`

Скрипт подгружает excel-файл Submits/submit.xlsx и формирует новый файл Submits/filled_submit.xlsx
