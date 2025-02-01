import threading
import time

import telebot
from telebot import types
from Token import token
from function import *
from templates import new_data_template, stocks

bot = telebot.TeleBot(token)
url_order = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
url_sale = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
url_stock = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
log = config_log()


@bot.message_handler(commands=['start'])
def start_menu(message):
    if not find_key(message.from_user.id):
        bot.send_message(message.chat.id, "Бот запущен! Напиши свой токен")
        bot.register_next_step_handler(message, to_database)
    else:
        bot.send_message(message.chat.id, "Вы уже начали использовать бота! Его функции тут /help")


@bot.message_handler(commands=['help'])
def help(message):
    markup = types.InlineKeyboardMarkup()  # Создаем разметку кнопок
    #создаем кнопки
    button1 = types.InlineKeyboardButton("Склады", callback_data='check_stocks')
    button2 = types.InlineKeyboardButton("Статистика за сегодня", callback_data='check_data')
    button3 = types.InlineKeyboardButton("Сменить токен", callback_data='change_token')
    button4 = types.InlineKeyboardButton("Артикулы", callback_data='nmId')
    button5 = types.InlineKeyboardButton("Статистика за вчера", callback_data='check_data_day')
    markup.add(button1, button4)
    markup.add(button2)
    markup.add(button5)
    markup.add(button3)  # Добавляем кнопки в разметку
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

    log.debug(f'Команда help')


#фУНКЦИЯ ВЫЗЫВАЕТСЯ АВТОМАТИЧЕСКИ ПОСЛЕ НАЖАТИЯ НА КНОПКИ
#каждая кнопка идентифицируется параметром callback_data
@bot.callback_query_handler(func=lambda call: True)
def callback_worker(call):
    if call.data == 'check_stocks':
        bot.send_message(call.message.chat.id, "Напиши артикул товара, который нужно найти на складах")
        bot.register_next_step_handler(call.message, stocks_data)  # Регистрируем следующий шаг
    elif call.data == 'check_data':
        check_data(call.message.chat.id)
    elif call.data == 'change_token':
        bot.send_message(call.message.chat.id, "Напиши новый токен")
        bot.register_next_step_handler(call.message, to_database)  # Регистрируем следующий шаг
    elif call.data == 'nmId':
        find_subject(call.message.chat.id)
    elif call.data == 'check_data_day':
        check_data(call.message.chat.id, day=1, name='Вчера')


def find_subject(user_id):
    key = find_key(user_id)
    data = get_data(url_stock, key, days=365 * 2)
    subjects = {
        'subjects': [],
        'nmId': []
    }
    log.debug("начинаем поиск артикулов")
    for subject in data:
        nmId = subject['nmId']
        sub = subject['subject']
        if nmId in subjects['nmId']:
            continue
        else:
            subjects['nmId'].append(nmId)
            subjects['subjects'].append(sub)

    log.debug("формируем ответ")
    mess = ""
    for i in range(len(subjects['nmId'])):
        mess += "\n" + subjects['subjects'][i] + "\n" + str(subjects['nmId'][i])

    log.debug("отправляем ответ")
    bot.send_message(user_id, f"Ваши артикулы:\n" + mess)


def find_key(user_id):
    log.debug(f'Подключаемся к БД для получения ключа от {user_id}')
    con = sqlite3.connect("wildberries.db")
    cursor = con.cursor()
    cursor.execute(f"SELECT * FROM orders_sales WHERE user_id = '{user_id}'")
    data = cursor.fetchone()
    if data:
        key = data[0]
    else:
        key = None
    cursor.close()
    con.commit()
    return key


def to_database(message):
    key = message.text
    user_id = message.from_user.id
    log.info(f'Получен ключ от {user_id}')
    if check_connection(key) == 'OK':
        con = sqlite3.connect("wildberries.db")
        cursor = con.cursor()
        cursor.execute(f"SELECT * FROM orders_sales WHERE user_id = '{user_id}'")
        data = cursor.fetchone()
        if data:
            log.info(f'Ключ уже записан идем на перезапись')
            update_data("key", key, user_id)
            log.info(f'Ключ перезаписан')
            bot.send_message(message.from_user.id, "Твой токен перезаписан")
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(user_id, "Секретный ключ был удалён.")
        else:
            log.info(f'Запись нового ключа')
            insert_data_to_database(url_order, url_sale, key, user_id)
            log.info(f'Успешно добавлен пользователь с id {user_id}')
            bot.send_message(user_id, "Ваш токен записан, теперь вы будете получать сообщение каждый раз когда в "
                                      "системе WB будет "
                                      "обновляться информация по вашим заказам")
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(user_id, "Секретный ключ был удалён.")
        cursor.close()
        con.commit()
    elif check_connection(key) == 401:
        bot.send_message(user_id, 'Вы ввели неправильный токен, проверьте его срок действия и '
                                  'правильность ввода и начните заново, выбрав нужную команду /help')
        log.info(f'Введен неверный ключ')
    else:
        bot.send_message(user_id, 'Произошла техническая ошибка, попробуйте позже')
        log.warning(f'Проблемы с доступом данных')


def stocks_data(message):
    user_id = message.from_user.id
    try:
        nmId = int(message.text)
    except Exception as err:
        log.warning(f'Пользователь ввел некорректный артикул {err}')
        bot.send_message(user_id, "Артикул товара должен быть числом")
        return
    key = find_key(user_id)

    log.info(f'Проверяем склады')
    data = get_data(url_stock, key, days=365 * 2)
    data.sort(key=lambda val: val["quantityFull"])
    data_filtered = list(filter(lambda val: val['nmId'] == nmId, data))
    if len(data_filtered) == 0:
        log.info(f'Пользователь ввел неверный артикул')
        bot.send_message(user_id, "Возможно вы ввели неверный артикул или вашего товара нет ни на одном складе")
        return

    mess = []
    quantity = 0
    inWayToClient = 0
    inWayFromClient = 0

    log.debug(f'Формируем сообщение')
    for stock in data_filtered:
        if stock['quantityFull'] != 0:
            param = {
                'stocks': stock['warehouseName'],
                'quantityFull': stock['quantityFull'],
                'quantity': stock['quantity'],
                'inWayToClient': stock['inWayToClient'],
                'inWayFromClient': stock['inWayFromClient']
            }
            mess.append(f"{''.join(stocks)}".format(**param))
            quantity += int(stock['quantity'])
            inWayToClient += int(stock['inWayToClient'])
            inWayFromClient += int(stock['inWayFromClient'])

    log.info(f'Отправляем сообщение')
    bot.send_message(user_id, f"{'\n\n'.join(mess)}"
                     + f"\n\nДоступно для продажи: {quantity}"
                     + f"\nВсего в пути до клиента: {inWayToClient}"
                     + f"\nВсего в пути от клиента: {inWayFromClient}"
                     + "\n/help")


def check_data(user_id, day: int = 0, name: str = 'Сегодня'):
    key = find_key(user_id)
    order_data = get_data(url_order, key, days=day + 1)
    log_order = [
        (sub['srid'], sub['isCancel'], sub['cancelDate'], sub['orderType'], sub['regionName'], sub['date']) for sub in
        order_data
    ]
    log.debug(f"Данные для сортировки отказов за {name} {log_order}")

    cancel_data = [data for data in order_data if data['isCancel'] and date_compare(data['cancelDate'], day)]
    log_cancel_data = [
        (sub['srid'], sub['isCancel'], sub['cancelDate'], sub['orderType'], sub['regionName'], sub['date']) for sub in
        cancel_data
    ]
    log.debug(f"Отказы за {name} {log_cancel_data}")

    sale_data = get_data(url_sale, key, days=day, flag='1')
    log_sale = [(sub['srid'], sub['saleID'][0], sub['orderType'], sub['regionName'], sub['date']) for sub in sale_data]
    log.debug(f"Продажи за {name} {log_sale}")
    num_sales = 0
    num_returned = 0
    for sale in sale_data:
        saleID = sale['saleID']
        if saleID[0] == 'S':
            num_sales += 1
        elif saleID[0] == 'R':
            num_returned += 1
    bot.send_message(user_id, f"{name} заказали {len(get_data(url_order, key, days=day, flag='1'))}шт."
                              f"\n{name} купили {num_sales}шт.\n{name} отказались от {len(cancel_data)}шт."
                              f"\n{name} вернули {num_returned}шт.\n/help")


@bot.message_handler(func=lambda message: True)
def echo(message):
    log.info(f'Получено сообщение от пользователя без команды')
    bot.send_message(message.from_user.id,
                     'Чтобы узнать что я умею нажми /help')


def check_server_updates():
    while True:
        #создаем список id и key
        con = sqlite3.connect("wildberries.db")
        cursor = con.cursor()
        cursor.execute(f"SELECT * FROM orders_sales")
        db = cursor.fetchall()
        id_list = [data[-1] for data in db]
        key_list = [data[0] for data in db]
        log.debug(f'Созданы списки id и key, {id_list}')
        cursor.close()
        con.commit()

        for id, key in zip(id_list, key_list):
            new_orders = check_new_data(url_order, key, id)
            if new_orders:
                log.info(f'Отправляем сообщения на новые заказы')
                index = len(get_data(url_order, key, days=0, flag='1'))
                for order in new_orders:
                    if order['isCancel']:
                        order_type = 'Отказ'
                    elif not order['isCancel']:
                        order_type = 'Заказ'
                    else:
                        order_type = None
                    date = datetime.datetime.strptime(order['date'], '%Y-%m-%dT%H:%M:%S')
                    param = {
                        'index': index,
                        'subject': order['subject'],
                        'nmId': order['nmId'],
                        'type': order_type,
                        'date': date,
                        'warehouseName': order['warehouseName'],
                        'regionName': order['regionName']
                    }
                    mess = f"{''.join(new_data_template)}".format(**param)
                    bot.send_message(id, mess)
                    log.info(f'Отправлено сообщение о заказе')
                    log.debug(f'{mess}')
                else:
                    update_data('last_order', new_orders[-1]['srid'], id)
                    log.debug(f'Обновлены данные')

            new_sales = check_new_data(url_sale, key, id)
            if new_sales:
                log.info(f'Отправляем сообщения на новые продажи')
                index = len(get_data(url_sale, key, days=0, flag='1'))
                for sale in new_sales:
                    saleID = sale['saleID']
                    if saleID[0] == 'S':
                        sale_type = 'Выкуп'
                    elif saleID[0] == 'R':
                        sale_type = 'Возврат'
                    else:
                        sale_type = None
                    date = datetime.datetime.strptime(sale['date'], '%Y-%m-%dT%H:%M:%S')
                    param = {
                        'index': index,
                        'subject': sale['subject'],
                        'nmId': sale['nmId'],
                        'type': sale_type,
                        'date': date,
                        'warehouseName': sale['warehouseName'],
                        'regionName': sale['regionName']
                    }
                    mess = f"{''.join(new_data_template)}".format(**param)
                    bot.send_message(id, mess)
                    log.info(f'Отправлено сообщение о продажах')
                    log.debug(f'{mess}')
                else:
                    update_data('last_sale', new_sales[-1]['srid'], id)
                    log.debug(f'Обновлены данные')
        # Задержка между проверками, например, 10 минут
        time.sleep(600)


def clear_log():
    time.sleep(24 * 60 * 60)
    with open('bot.log', 'w') as log_file:
        pass
    log.debug(f'Новые логи')


def main():
    try:
        # Очистить файл через день
        threading.Thread(target=clear_log, daemon=True).start()
        # Запуск потока для проверки обновлений на сервере
        threading.Thread(target=check_server_updates, daemon=True).start()
        # Запуск бота
        bot.polling(none_stop=True, interval=0)
    except requests.exceptions.ReadTimeout:
        log.info(f'Время ожидания превышено')
        time.sleep(300)
        log.info(f'Запуск кода через 5 мин')
        main()
    except Exception as err:
        print(err)
