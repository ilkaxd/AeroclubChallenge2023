from additional_classes import Aeroport, City

import os
import datetime as dt

import pandas as pd
import joblib

from catboost import CatBoostClassifier


# Глобальные параметры
submits_folder = 'Submits'
submit_file = os.path.join(submits_folder, 'submit.xlsx')
filled_submit_file = os.path.join(submits_folder, 'filled_submit.xlsx')

models_folder = 'Models'
selected_model = os.path.join(
    models_folder,
    'gb_model'
)
selected_encoder = os.path.join(
    models_folder,
    'arrays_encoders.joblib'
)

locations_file = os.path.join('Data', 'Locations_UTC.xlsx')
datetime_format = '%Y-%m-%d %H:%M:%S.%f'

cities_idx = {}
cities_code = {}
aeroports = {}


def main():
    # Первоначальные загрузки
    load_cities()
    submit = load_df()
    model = load_model()
    encoders = load_encoder()

    x_columns = [
        'ClientID',
        'TravellerGrade',
        'From',
        'To',
        'FlightCompany',
        'FlightDuration',
        'SegmentCount',
        'DeltaActualRequest',
        'DepartureDateDayOfWeek',
        'ArrivalDateDayOfWeek',
        'Amount',
        'class',
        'IsBaggage',
        'isRefundPermitted',
        'isExchangePermitted',
        'isDiscount',
        'InTravelPolicy',
    ]
    filled_submit = make_prediction(submit, model, encoders, x_columns)

    # Сохраняем результат
    filled_submit.to_excel(filled_submit_file)


def load_cities():
    '''Парсим файл Locations_UTC.xlsx'''
    cities_df = pd.read_excel(
        locations_file,
        engine='openpyxl',
        sheet_name='City'
    )
    aeroports_df = pd.read_excel(
        locations_file,
        engine='openpyxl',
        sheet_name='Airport'
    )

    for idx, country, name, name_english, code, timeZone in cities_df.values:
        city = City(idx, name, name_english, country, code, timeZone)
        cities_idx[idx] = city
        cities_code[code] = city

    for idx, cityIdx, name, name_english, code in aeroports_df.values:
        try:
            city = cities_idx[cityIdx]
            aeroport = Aeroport(idx, city, name, name_english, code)
            city.aeroports.append(aeroport)
            aeroports[code] = aeroport
        except Exception:
            print('Нет города для аэропорта', name)


def load_df():
    '''Подгружаем сабмит'''
    return pd.read_excel(submit_file, engine='openpyxl').set_index('ID')


def load_model():
    '''Подгружаем модель'''
    model = CatBoostClassifier()
    model.load_model(selected_model)
    return model


def load_encoder():
    '''Подгружаем кодировщики для категориальных признаков'''
    return joblib.load(selected_encoder)


def make_prediction(
        submit,
        model,
        encoders,
        x_columns
):
    '''
    Выполняем прогноз

    Arguments:
        - submit - набор данных для заполнения
        - model - используемая модель
        - encoders - кодировщики
        - x_columns - используемые столбцы
    '''
    # Подгоняем наименование
    right_submit = submit.rename({
        'ValueRu': 'TravellerGrade',
        'FligtOption': 'FlightOption',
        'Position ( from 1 to n)': 'SentOption'
    }, axis=1)

    # Результаты работы модели
    predictions = []
    # Проходим по каждому запросу с предложенными вариантами
    for request in right_submit.RequestID.unique():
        # Вычленяем интересующую подгруппу
        local_submit = right_submit.query('RequestID == @request').copy()
        # Преобразуем форматы времени
        for column in [
                'RequestDate',
                'RequestDepartureDate', 'RequestReturnDate',
                'DepartureDate', 'ArrivalDate',
                'ReturnDepatrureDate', 'ReturnArrivalDate'
        ]:
            transform_date(local_submit, column)

        # Выполняем деление маршрута
        splitted_local_submit = transform_df(local_submit)

        # Если какая-то ошибка была
        if (splitted_local_submit.shape[0] == 0):
            predictions.append(1)
            continue

        # Добавляем фичи
        add_simple_features(splitted_local_submit)

        # Заполняем пропуски
        splitted_local_submit['TravellerGrade'] = splitted_local_submit[
            'TravellerGrade'
        ].fillna('-1').astype('str')
        splitted_local_submit['isRefundPermitted'] = splitted_local_submit[
            'isRefundPermitted'
        ].fillna(0)
        splitted_local_submit['isExchangePermitted'] = splitted_local_submit[
            'isRefundPermitted'
        ].fillna(0)

        # Кодируемся
        for column, enc in encoders.items():
            splitted_local_submit[column] = transform_encoder(
                splitted_local_submit[column], enc
            )

        # Подгоняем формат данных для категориальных признаков
        for column in [
            'TravellerGrade',
            'FlightCompany',
            'FlightDuration',
            'DepartureDateDayOfWeek',
            'ArrivalDateDayOfWeek',
            'class',
            'IsBaggage',
            'isRefundPermitted',
            'isExchangePermitted',
            'isDiscount',
            'InTravelPolicy'
        ]:
            splitted_local_submit[column] = splitted_local_submit[column].astype('int')

        # Оставим только нужные признаки
        x = splitted_local_submit[x_columns]

        # Сохраняем только вероятность выбора предложения
        local_predictions = [pred[1] for pred in model.predict_proba(x)]

        # Летели в 2 направлениях
        if splitted_local_submit.shape[0] != local_submit.shape[0]:
            local_predictions = calculate_sum_predictions(local_predictions)

        # Назначаем порядковые значения на основе вероятностей
        options_order = sort_args(local_predictions)
        predictions += options_order
    filled_submit = submit.copy()
    filled_submit['Position ( from 1 to n)'] = predictions
    return filled_submit


def transform_date(df, column, format_=datetime_format):
    '''Подгоняем столбец к заданному формуту даты-времени'''
    df[column] = pd.to_datetime(df[column], format=format_)


def transform_df(df):
    '''Делим DataFrame на отдельные направления'''
    # Сформированные строки
    one_way_df = []
    # Проходим по каждой строке
    for index in range(len(df)):
        row = df.iloc[index]

        # Вычленяем направления
        splitted_routes = row['SearchRoute'].split('/')
        # Вычленяем сегменты
        splitted_flight_option = row['FlightOption'].split('/')

        # Проходим по каждому маршруту, 0 - туда, 1 - обратно
        for i, search_route in enumerate(splitted_routes):
            # Определяем города, откуда куда
            # !!! Может стоит добавить признак указания аэропорта
            from_name = search_route[:3]
            try:
                from_city = get_city(from_name)
            except Exception:
                print(f'Точка отправления {from_name} не найдена')
                continue

            to_name = search_route[3:]
            try:
                to_city = get_city(to_name)
            except Exception:
                print(f'Точка прибытия {to_name} не найдена')
                continue

            # Какие самолёты, использовались в данном направлении
            flight_options = []
            try:
                while len(splitted_flight_option) > 0:
                    # Берём путь
                    path = splitted_flight_option.pop(0)
                    # Компания, маршрут, дата отправления
                    number, direction, time = path.split()
                    flight_options.append(path)
                    # Если конечная точка маршрута совпадает с местом прибытия,
                    # значит мы долетеле до места назначения
                    to_aeroport = aeroports[direction[3:]]
                    if to_aeroport in to_city.aeroports:
                        break
            except Exception as e:
                print(e)
                continue

            # Цену вычисляем пропорционально количеству затраченных сегментов
            # !!! Можно просто поделить пополам
            ammount = row['Amount'] * len(flight_options) / row['SegmentCount']

            # Правильно подбиваем даты
            if i == 0:
                request_departure_date = row['RequestDepartureDate']
                departure_date = row['DepartureDate']
                arrival_date = row['ArrivalDate']
            elif i == 1:
                request_departure_date = row['RequestReturnDate']
                departure_date = row['ReturnDepatrureDate']
                arrival_date = row['ReturnArrivalDate']

            # Вычисляем длительность полёта
            try:
                duration = calculate_duration(
                    departure_date, arrival_date,
                    from_city, to_city
                )
            except Exception as e:
                print(e, from_city, to_city)

            # Добавляем всё в правильной последовательности
            one_way_df.append([
                row['RequestID'],
                row['RequestDate'],
                row['ClientID'],
                row['TravellerGrade'],
                from_city.idx,
                to_city.idx,
                request_departure_date,
                '/'.join(flight_options),
                len(flight_options),
                departure_date,
                arrival_date,
                duration,
                ammount,
                row['class'],
                row['IsBaggage'],
                row['isRefundPermitted'],
                row['isExchangePermitted'],
                row['isDiscount'],
                row['InTravelPolicy'],

                row['SentOption'],
            ])

    return pd.DataFrame(
        data=one_way_df,
        columns=[
            'RequestID',
            'RequestDate',
            'ClientID',
            'TravellerGrade',
            'From',
            'To',
            'RequestDepartureDate',
            'FlightOption',
            'SegmentCount',
            'DepartureDate',
            'ArrivalDate',
            'FlightDuration',
            'Amount',
            'class',
            'IsBaggage',
            'isRefundPermitted',
            'isExchangePermitted',
            'isDiscount',
            'InTravelPolicy',

            'SentOption',
        ]
    )


def get_city(name):
    '''
    Получаем город из столбцов From, To
    '''
    name = name.strip()
    if name in cities_code.keys():
        return cities_code[name]
    if name in aeroports.keys():
        return aeroports[name].city
    raise Exception


def calculate_duration(departure, arrival, from_city, to_city):
    '''
    Вычисляем длительность полёта:

    Arguments:
        - departure - местое время вылета
        - arrival - местное время прибытия
        - город отправления
        - город прибытия
    '''
    departure_with_tz = departure - dt.timedelta(hours=from_city.timeZone)
    arrival_with_tz = arrival - dt.timedelta(hours=to_city.timeZone)

    return (arrival_with_tz - departure_with_tz)


def add_simple_features(df):
    '''
    Добавляем простые признаки:
        - Разница между фактическим вылётом и запрашиваемым в секундах
        - Время полёта в часах
        - Обозначение перевозящей компании
        - День недели для вылета
        - День недели для прилёта
    '''
    df['DeltaActualRequest'] = (
        df['DepartureDate'] - df['RequestDepartureDate']
    ).dt.seconds
    df['FlightDuration'] = df['FlightDuration'].dt.seconds // 3600
    df['FlightCompany'] = df.FlightOption.apply(lambda x: x[:2])
    df['DepartureDateDayOfWeek'] = df['DepartureDate'].dt.dayofweek
    df['ArrivalDateDayOfWeek'] = df['ArrivalDate'].dt.dayofweek


def transform_encoder(series, encoder):
    '''
    Фикс бага с невозможностью сериализации OrdinalEncoding
    '''
    result = []
    for value in series:
        result.append(encoder.index(value))
    return result


def calculate_sum_predictions(predictions):
    '''Вычисляем вероятность перелёта туда и обратно'''
    return [
        predictions[i] + predictions[i + 1]
        for i in range(0, len(predictions), 2)
    ]


def sort_args(probs):
    '''Сортируем вероятности выбора по убыванию'''
    sorted_probs = sorted(probs, reverse=True)
    return [sorted_probs.index(prob) + 1 for prob in probs]


if __name__ == '__main__':
    main()
    print('Конец программы')
