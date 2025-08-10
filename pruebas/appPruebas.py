from flask import Flask, render_template, request, redirect, url_for, flash
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key' 

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'hola123',
}

def get_connection(database=None):
    config = db_config.copy()
    if database:
        config['database'] = database
    return mysql.connector.connect(**config)

def get_databases():
    exclude = {'information_schema', 'mysql', 'performance_schema', 'sys'}
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            return [db[0] for db in cursor.fetchall() if db[0] not in exclude]

@app.route('/')
def index():
    return render_template('index.html', databases=get_databases())

@app.route('/database/<db_name>')
def database(db_name):
    return render_template('database.html', db_name=db_name, databases=get_databases())

@app.route('/create_database', methods=['POST'])
def create_database():
    db_name = request.form['db_name']
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{db_name}`")
    return redirect(url_for('index'))

@app.route('/database/<db_name>/tables')
def view_tables(db_name):
    databases = get_databases()
    with get_connection(db_name) as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SHOW TABLES")
            tables = [t[f'Tables_in_{db_name}'] for t in cursor.fetchall()]
            tablas_con_registros = []
            for table in tables:
                cursor.execute(f"SELECT * FROM `{table}`")
                registros = cursor.fetchall()
                columnas = [desc[0] for desc in cursor.description]
                # Obtener el nombre de la PK
                cursor.execute(f"SHOW KEYS FROM `{table}` WHERE Key_name = 'PRIMARY'")
                pk_info = cursor.fetchone()
                pk_col = pk_info['Column_name'] if pk_info else None
                tablas_con_registros.append({
                    'nombre': table,
                    'columnas': columnas,
                    'registros': registros,
                    'pk': pk_col
                })
    return render_template('tables.html', db_name=db_name, databases=databases, tablas_con_registros=tablas_con_registros)

@app.route('/database/<db_name>/create_table', methods=['GET', 'POST'])
def create_table(db_name):
    databases = get_databases()
    # Si vienen parámetros por GET, úsalos para prellenar
    default_table_name = request.args.get('table_name', 'usuarios')
    num_columns = int(request.args.get('num_columns', 3))
    # Genera columnas vacías si no hay POST
    default_columns = [
        {"name": f"columna{i+1}", "type": "VARCHAR", "unique": False, "pk": False, "null": True}
        for i in range(num_columns)
    ]
    if request.method == 'POST':
        try:
            table_name = request.form['table_name']
            num_columns = int(request.form['num_columns'])
            columns = []
            pk_columns = []
            for i in range(num_columns):
                name = request.form[f'col_name_{i}']
                col_type = request.form[f'col_type_{i}']
                unique = 'UNIQUE' if f'col_unique_{i}' in request.form else ''
                null = 'NULL' if f'col_null_{i}' in request.form else 'NOT NULL'
                pk = f'col_pk_{i}' in request.form
                if col_type == 'VARCHAR':
                    col_def = f"`{name}` VARCHAR(255) {unique} {null}"
                else:
                    col_def = f"`{name}` {col_type} {unique} {null}"
                columns.append(col_def)
                if pk:
                    pk_columns.append(f"`{name}`")
            pk_sql = f", PRIMARY KEY ({', '.join(pk_columns)})" if pk_columns else ""
            sql = f"CREATE TABLE `{table_name}` ({', '.join(columns)}{pk_sql})"
            with get_connection(db_name) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql)
            return redirect(url_for('view_tables', db_name=db_name))
        except Exception as e:
            flash(f"Error al crear la tabla: {e}")
            return redirect(url_for('create_table', db_name=db_name))
    return render_template(
        'create_table.html',
        db_name=db_name,
        databases=databases,
        default_table_name=default_table_name,
        num_columns=num_columns,
        default_columns=default_columns
    )

@app.route('/database/<db_name>/<table_name>/create_registro', methods=['GET', 'POST'])
def create_registro(db_name, table_name):
    databases = get_databases()
    pk_value = request.args.get('pk_value')
    registro = None
    with get_connection(db_name) as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            columnas = cursor.fetchall()
            # Obtener nombre de la PK
            cursor.execute(f"SHOW KEYS FROM `{table_name}` WHERE Key_name = 'PRIMARY'")
            pk_info = cursor.fetchone()
            pk_name = pk_info['Column_name'] if pk_info else None
            # Si viene pk_value, busca el registro
            if pk_value and pk_name:
                cursor.execute(f"SELECT * FROM `{table_name}` WHERE `{pk_name}` = %s", (pk_value,))
                registro = cursor.fetchone()
    if request.method == 'POST':
        try:
            campos = [col['Field'] for col in columnas]
            valores = [request.form.get(campo) for campo in campos]
            # Detectar si es update o insert
            if pk_name and request.form.get(pk_name):
                # Verificar si existe el registro
                with get_connection(db_name) as conn:
                    with conn.cursor(dictionary=True) as cursor:
                        cursor.execute(f"SELECT * FROM `{table_name}` WHERE `{pk_name}` = %s", (request.form.get(pk_name),))
                        existe = cursor.fetchone()
                if existe:
                    # UPDATE
                    set_sql = ', '.join(f"`{campo}` = %s" for campo in campos)
                    sql = f"UPDATE `{table_name}` SET {set_sql} WHERE `{pk_name}` = %s"
                    valores_update = valores + [request.form.get(pk_name)]
                    with get_connection(db_name) as conn:
                        with conn.cursor() as cursor:
                            cursor.execute(sql, valores_update)
                            conn.commit()
                    flash("Registro actualizado correctamente.")
                    return redirect(url_for('view_tables', db_name=db_name))
            # Si no existe, INSERT
            placeholders = ', '.join(['%s'] * len(campos))
            campos_sql = ', '.join(f"`{c}`" for c in campos)
            sql = f"INSERT INTO `{table_name}` ({campos_sql}) VALUES ({placeholders})"
            with get_connection(db_name) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(sql, valores)
                    conn.commit()
            flash("Registro agregado correctamente.")
            return redirect(url_for('view_tables', db_name=db_name))
        except Exception as e:
            flash(f"Error al guardar el registro: {e}")
    return render_template(
        'create_registro.html',
        db_name=db_name,
        table_name=table_name,
        databases=databases,
        columnas=columnas,
        registro=registro
    )

@app.route('/database/<db_name>/<table_name>/delete_registro', methods=['POST'])
def delete_registro(db_name, table_name):
    pk_value = request.form.get('pk_value')
    # Obtener el nombre de la PK
    with get_connection(db_name) as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(f"SHOW KEYS FROM `{table_name}` WHERE Key_name = 'PRIMARY'")
            pk_info = cursor.fetchone()
            if not pk_info:
                flash("No se encontró clave primaria para esta tabla.")
                return redirect(url_for('view_tables', db_name=db_name))
            pk_name = pk_info['Column_name']
            sql = f"DELETE FROM `{table_name}` WHERE `{pk_name}` = %s"
            try:
                cursor.execute(sql, (pk_value,))
                conn.commit()
                flash("Registro eliminado correctamente.")
            except Exception as e:
                flash(f"Error al eliminar el registro: {e}")
    return redirect(url_for('view_tables', db_name=db_name))

@app.route('/database/<db_name>/<table_name>/accion_registro', methods=['POST'])
def accion_registro(db_name, table_name):
    pk_value = request.form.get('pk_value')
    accion = request.form.get('accion')
    if accion == 'eliminar':
        # Lógica de eliminar (igual que tu delete_registro)
        with get_connection(db_name) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(f"SHOW KEYS FROM `{table_name}` WHERE Key_name = 'PRIMARY'")
                pk_info = cursor.fetchone()
                if not pk_info:
                    flash("No se encontró clave primaria para esta tabla.")
                    return redirect(url_for('view_tables', db_name=db_name))
                pk_name = pk_info['Column_name']
                sql = f"DELETE FROM `{table_name}` WHERE `{pk_name}` = %s"
                try:
                    cursor.execute(sql, (pk_value,))
                    conn.commit()
                    flash("Registro eliminado correctamente.")
                except Exception as e:
                    flash(f"Error al eliminar el registro: {e}")
        return redirect(url_for('view_tables', db_name=db_name))
    elif accion == 'modificar':
        # Redirige a create_registro con el pk_value
        return redirect(url_for('create_registro', db_name=db_name, table_name=table_name, pk_value=pk_value))
@app.route('/database/<db_name>/<table_name>/add_column', methods=['GET', 'POST'])
def add_column(db_name, table_name):
    databases = get_databases()
    col_name = request.args.get('col_name') or request.form.get('col_name')
    columna = None

    # Si viene col_name, busca si existe la columna
    if col_name:
        with get_connection(db_name) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute(f"SHOW COLUMNS FROM `{table_name}` WHERE Field = %s", (col_name,))
                columna = cursor.fetchone()

    if request.method == 'POST':
        col_type = request.form['col_type']
        unique = 'UNIQUE' if 'col_unique' in request.form else ''
        null = 'NULL' if 'col_null' in request.form else 'NOT NULL'
        pk = 'col_primary' in request.form

        if columna:
            # MODIFICAR columna existente
            try:
                with get_connection(db_name) as conn:
                    with conn.cursor() as cursor:
                        if col_type == 'VARCHAR':
                            col_def = f"`{col_name}` VARCHAR(255) {unique} {null}"
                        else:
                            col_def = f"`{col_name}` {col_type} {unique} {null}"
                        cursor.execute(f"ALTER TABLE `{table_name}` MODIFY COLUMN {col_def}")
                        # Opcional: manejar PK aquí si quieres
                        conn.commit()
                flash("Columna modificada correctamente.")
                return redirect(url_for('view_tables', db_name=db_name))
            except Exception as e:
                flash(f"Error al modificar la columna: {e}")
        else:
            # AGREGAR columna nueva
            if col_type == 'VARCHAR':
                col_def = f"`{col_name}` VARCHAR(255) {unique} {null}"
            else:
                col_def = f"`{col_name}` {col_type} {unique} {null}"
            try:
                with get_connection(db_name) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN {col_def}")
                        if pk:
                            cursor.execute(f"ALTER TABLE `{table_name}` ADD PRIMARY KEY (`{col_name}`)")
                        conn.commit()
                flash("Columna agregada correctamente.")
                return redirect(url_for('view_tables', db_name=db_name))
            except Exception as e:
                flash(f"Error al agregar la columna: {e}")

    return render_template(
        'add_column.html',
        db_name=db_name,
        table_name=table_name,
        databases=databases,
        columna=columna
    )

@app.route('/database/<db_name>/<table_name>/modificar_columna', methods=['GET', 'POST'])
def modificar_columna(db_name, table_name):
    col_name = request.args.get('col_name')
    # Aquí mostrarás el formulario para editar la columna col_name
    # ...
    return render_template('modificar_columna.html', db_name=db_name, table_name=table_name, col_name=col_name)

@app.route('/database/<db_name>/<table_name>/redirigir_modificar_columna', methods=['GET'])
def redirigir_modificar_columna(db_name, table_name):
    col_name = request.args.get('col_name')
    accion = request.args.get('accion')
    existe = False
    # Verifica si la columna existe
    with get_connection(db_name) as conn:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute(f"SHOW COLUMNS FROM `{table_name}` WHERE Field = %s", (col_name,))
            if cursor.fetchone():
                existe = True
    if accion == "eliminar":
        if existe:
            try:
                with get_connection(db_name) as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(f"ALTER TABLE `{table_name}` DROP COLUMN `{col_name}`")
                        conn.commit()
                flash("Columna eliminada correctamente.")
            except Exception as e:
                flash(f"Error al eliminar la columna: {e}")
        else:
            flash("La columna no existe.")
        return redirect(url_for('view_tables', db_name=db_name))
    elif accion == "modificar":
        if existe:
            return redirect(url_for('add_column', db_name=db_name, table_name=table_name, col_name=col_name))
        else:
            flash("La columna no existe.")
            return redirect(url_for('view_tables', db_name=db_name))
    else:
        return redirect(url_for('view_tables', db_name=db_name))

@app.route('/database/<db_name>/<table_name>/eliminar_tabla', methods=['POST'])
def eliminar_tabla(db_name, table_name):
    try:
        with get_connection(db_name) as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP TABLE `{table_name}`")
                conn.commit()
        flash(f"Tabla '{table_name}' eliminada correctamente.")
    except Exception as e:
        flash(f"Error al eliminar la tabla: {e}")
    return redirect(url_for('view_tables', db_name=db_name))

@app.route('/database/<db_name>/info')
def database_info(db_name):
    databases = get_databases()
    # Aquí puedes agregar más lógica para mostrar información de la base de datos si quieres
    return render_template('database_info.html', db_name=db_name, databases=databases)

@app.route('/database/<db_name>/eliminar_base', methods=['POST'])
def eliminar_base(db_name):
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP DATABASE `{db_name}`")
                conn.commit()
        flash(f"Base de datos '{db_name}' eliminada correctamente.")
    except Exception as e:
        flash(f"Error al eliminar la base de datos: {e}")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)