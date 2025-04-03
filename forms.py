from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, SubmitField
from wtforms.validators import DataRequired

class CategoriaForm(FlaskForm):
    nome = StringField('Nome', validators=[DataRequired()])
    tipo = SelectField('Tipo', 
                       choices=[('entrada', 'Entrada'), ('saida', 'Saída')], 
                       validators=[DataRequired()])
    submit = SubmitField('Enviar')