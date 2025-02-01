new_data_template = [
    "{type} [{index}]",
    "\nТовар: {subject}"
    "\nАртикул: {nmId}"
    "\nДата заказа: {date}",
    "\n{warehouseName} → {regionName}",
    "\n/help"
]

stocks = [
    "{stocks} - {quantityFull}",
    "\n\t\tдоступное для продажи: {quantity}"
    "\n\t\tв пути к клиенту: {inWayToClient}"
    "\n\t\tв пути от клиента: {inWayFromClient}"
]