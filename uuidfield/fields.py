import uuid

from django import forms
from django.db.models import Field, SubfieldBase
from django.utils.encoding import smart_unicode
from binascii import unhexlify

try:
    # psycopg2 needs us to register the uuid type
    import psycopg2
    psycopg2.extras.register_uuid()
except (ImportError, AttributeError):
    pass

class UUIDField(Field):
    """
    A field which stores a UUID value in hex format. This may also have
    the Boolean attribute 'auto' which will set the value on initial save to a
    new UUID value (calculated using the UUID1 method). Note that while all
    UUIDs are expected to be unique we enforce this with a DB constraint.
    """
    # TODO: Add binary storage support for other database types as well
    __metaclass__ = SubfieldBase

    def __init__(self, version=4, node=None, clock_seq=None,
            namespace=None, name=None, auto=False, *args, **kwargs):
        assert version in (1, 3, 4, 5), "UUID version %s is not supported." % version
        self.auto = auto
        self.version = version
        # We store UUIDs in hex format, which is fixed at 32 characters.
        kwargs['max_length'] = 32
        if auto:
            # Do not let the user edit UUIDs if they are auto-assigned.
            kwargs['editable'] = False
            kwargs['blank'] = True
            kwargs['unique'] = True
        if version == 1:
            self.node, self.clock_seq = node, clock_seq
        elif version in (3, 5):
            self.namespace, self.name = namespace, name
        super(UUIDField, self).__init__(*args, **kwargs)

    def _create_uuid(self):
        if self.version == 1:
            args = (self.node, self.clock_seq)
        elif self.version in (3, 5):
            error = None
            if self.name is None:
                error_attr = 'name'
            elif self.namespace is None:
                error_attr = 'namespace'
            if error is not None:
                raise ValueError("The %s parameter of %s needs to be set." %
                                 (error_attr, self))
            if not isinstance(self.namespace, uuid.UUID):
                raise ValueError("The name parameter of %s must be an "
                                 "UUID instance." % self)
            args = (self.namespace, self.name)
        else:
            args = ()
        return getattr(uuid, 'uuid%s' % self.version)(*args)

    def db_type(self, connection=None):
        """
        Return the special uuid data type on Postgres databases.
        """
        if connection and 'postgres' in connection.vendor:
            return 'uuid'
        if connection and 'mysql' in connection.vendor:
            return 'binary(16)'
        return 'char(%s)' % self.max_length

    def _db_is_binary(self, con):
        return self.db_type(connection=con) == 'binary(16)'

    def pre_save(self, model_instance, add):
        """
        This is used to ensure that we auto-set values if required.
        See CharField.pre_save
        """
        value = getattr(model_instance, self.attname, None)
        if self.auto and add and not value:
            # Assign a new value for this attribute if required.
            uuid = self._create_uuid()
            setattr(model_instance, self.attname, uuid)
            value = uuid.hex
        return value

    def get_db_prep_value(self, value, connection, prepared=False):
        """
        Casts uuid.UUID values into the format expected by the back end
        """
        binary = self._db_is_binary(connection)

        if isinstance(value, uuid.UUID):
            if binary:
                return value.bytes # binary field, return raw bytes
            #return str(value)
            return value.hex

        value.lower()
        # support pretty UUIDs with dashed syntax as well
        value = value.replace('-', '')

        # unhex the value if using binary fields
        if binary:
            #return uuid.UUID(value).bytes
            return unhexlify(value)

        return value

    def value_to_string(self, obj):
        val = self._get_val_from_obj(obj)
        if val is None:
            data = u''
        else:
            data = unicode(val)
        return data

    def to_python(self, value):
        """
        Returns a ``UUID`` instance from the value returned by the
        database.
        """
        if not value:
            return None

        if isinstance(value, uuid.UUID):
            return value

        if len(value) == 16: # assume binary uuid
            return uuid.UUID(bytes=value)

        return uuid.UUID(value)

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.CharField,
            'max_length': self.max_length,
        }
        defaults.update(kwargs)
        return super(UUIDField, self).formfield(**defaults)

try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], [r"^uuidfield\.fields\.UUIDField"])
except ImportError:
    pass
