import logging
import requests
import datetime
import sqlite3


def config_log():
    log = logging.getLogger('Bot')
    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler("bot.log", 'w', 'utf-8')

    stream_formater = logging.Formatter('%(levelname)s - %(message)s')
    file_formater = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d %m %Y - %H:%M')

    stream_handler.setFormatter(stream_formater)
    file_handler.setFormatter(file_formater)

    log.addHandler(stream_handler)
    log.addHandler(file_handler)

    log.setLevel(logging.DEBUG)
    stream_handler.setLevel(logging.INFO)
    file_handler.setLevel(logging.DEBUG)

    return log


log = config_log()


def date_compare(date: str, day: int) -> bool:
    if (datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S').date()
            == (datetime.datetime.now() - datetime.timedelta(days=day)).date()):
        return True
    else:
        return False


def check_connection(key):
    log.debug(f'Проверка подключения')
    url = 'https://common-api.wildberries.ru/ping'
    headers = {
        "Authorization": key
    }
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except Exception as err:
        log.error(f'{err}')
        return err
    if response.status_code == 200:
        log.debug(f'Успешно')
        return response.json()["Status"]
    else:
        log.warning(f'Что-то не-так с сайтом {response.status_code}')
        return response.status_code


def get_data(url: str, key: str, days: int = 1, flag: str = '0') -> list:
    # order_type: 'full' - all data
    #             'order' - data by order
    #             'cancel' - data by cancel
    data = []
    now_time = datetime.date.today()
    delta = datetime.timedelta(days=days)
    delta_time = now_time - delta
    dateFrom = delta_time.strftime("%Y-%m-%d")
    url_param = ''.join([url, "?dateFrom=", dateFrom, '&', 'flag=', flag])
    headers = {
        "Authorization": key
    }
    try:
        log.debug(f'Проход по ссылке {url_param}')
        response = requests.get(url_param, headers=headers, timeout=60)
    except requests.exceptions.Timeout:
        log.error(f"Превышено время ожидания")
        return data
    except requests.exceptions.RequestException as e:
        log.error(f"Произошла ошибка: {e}")
        return data
    if response.status_code == 200:
        data = response.json()
        if url[-6:] == 'orders':
            order_data = [(order, order['date']) for order in data if not order['isCancel']]
            cancel_data = [(cancel, cancel['cancelDate']) for cancel in data if cancel['isCancel']]
            order_data.extend(cancel_data)
            order_data.sort(key=lambda val: datetime.datetime.strptime(val[1], '%Y-%m-%dT%H:%M:%S'))
            data = [dt[0] for dt in order_data]
            log.debug(f'Получены данные из функции get_data, список srid {[obj["srid"] for obj in data]}')

        elif url[-6:] == '/sales':
            data.sort(key=lambda val: datetime.datetime.strptime(val['date'], '%Y-%m-%dT%H:%M:%S'))
            log.debug(f'Получены данные из функции get_data, список srid {[obj["srid"] for obj in data]}')

        elif url[-6:] == 'stocks':
            log.debug(f'Получены данные из функции get_data, список stocks {[obj["warehouseName"] for obj in data]}')

    elif response.status_code == 401:
        log.warning("Пользователь не авторизован")
    else:
        log.error(f"Ошибка доступа к сайту: {response.status_code}")
    return data


def insert_data_to_database(url_orders: str, url_sales: str, key: str, user_id: str):
    orders = get_data(url_orders, key)
    log.debug(f'Получены заказы в функции insert_data_to_database')
    sales = get_data(url_sales, key)
    log.debug(f'Получены продажи в функции insert_data_to_database')

    if orders:
        last_order = orders[-1]["srid"]
    else:
        last_order = None
    if sales:
        last_sale = sales[-1]["srid"]
    else:
        last_sale = None
    obj = (key, last_order, last_sale, user_id)

    log.debug(f'подключение к БД для вставки данных')
    con = sqlite3.connect("wildberries.db")
    cursor = con.cursor()
    cursor.execute("INSERT INTO orders_sales (key, last_order, last_sale, user_id) VALUES (?, ?, ?, ?)", obj)
    cursor.close()
    con.commit()
    log.info(f'данные вставлены {obj[1:]}')


def update_data(field: str, data: str, user_id: str):
    log.debug(f'подключение к БД для обновления данных')
    con = sqlite3.connect("wildberries.db")
    cursor = con.cursor()
    cursor.execute(f"UPDATE orders_sales SET {field} ='{data}' WHERE user_id='{user_id}'")
    cursor.close()
    con.commit()
    log.info(f'Для пользователя {user_id} обновлены данные {field}')


def check_new_data(url: str, key: str, user_id: str):
    #url определяет что будем проверять заказы или продажы по последнему слову в адресе
    field = ''.join(["last_", url.split("/")[-1][:-1]])
    log.info(f'определяется поле {field}')

    data = get_data(url, key)
    log.debug(f'получены данные для проверки новых')

    data.reverse()
    log.debug(f'поменяли направление')

    srid_list = [obj["srid"] for obj in data]
    log.info(f'получен список srid {srid_list}')

    log.debug(f'подключаемся к БД')
    con = sqlite3.connect("wildberries.db")
    cursor = con.cursor()
    cursor.execute(f"SELECT * FROM orders_sales WHERE user_id='{user_id}'")
    obj = cursor.fetchone()
    log.info(f'получены данные из БД  {obj[1:]}')

    num = 11 - len(field)
    last_srid = obj[num]
    log.debug(f'last_srid {last_srid}')
    cursor.close()
    con.commit()

    new_data = []
    for dat, srid in zip(data, srid_list):
        if srid == last_srid:
            break
        else:
            new_data.append(dat)
    new_data.reverse()
    if data:
        log.info(f'Найдены новые данные {[obj["srid"] for obj in new_data]}')
    else:
        log.info(f'Новых данных нет')
    return new_data






